"""TD-17 MIDI-to-audio latency calibration (research R-06).

The TD-17 sends MIDI at a different time relative to its audio for each pad (the kick
differs from the others by about 20 ms), and in real playing the attack of a hit is hard
to find in the ringing of earlier hits. So the latency is measured once per pad from hits
played one at a time, and ground truth = MIDI time (stream clock) + that latency."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from poc.domain import EVALUATED_INSTRUMENTS
from poc.errors import PocError
from poc.recording.note_map import NoteMap, drop_double_triggers

ENVELOPE_MS = 0.5
SEARCH_BEFORE_MS = 150.0  # the TD-17 audio may start before the MIDI note arrives
SEARCH_AFTER_MS = 100.0
BASELINE_MS = 20.0  # silence before the search window
ISOLATION_BEFORE_SEC = 0.3
ISOLATION_AFTER_SEC = 0.15
# Onset = last crossing of baseline + 2% of the rise before the peak. With 15%, the kick and
# snare head (whose low body peaks late) read about 10 ms later than the rim and hi-hat;
# at 5% or less all TD-17 pads agree within 2 ms (research R-06).
ONSET_FRACTION = 0.02
OUTLIER_MS = 3.0
MIN_HITS = 3
MAX_STD_MS = 1.0  # SC-008


class CalibrationError(PocError):
    """The calibration recording cannot give a precise latency for every instrument."""


@dataclass(frozen=True)
class Calibration:
    offsets_ms: dict[str, float]  # audio onset - MIDI time, per evaluated instrument
    note_offsets_ms: dict[int, float]  # the same per MIDI note (notes hit MIN_HITS+ times)
    std_ms: dict[str, float]  # spread per instrument (SC-008)
    counts: dict[str, int]
    outliers: int

    def offset_sec(self, note: int, instrument: str) -> float:
        return self.note_offsets_ms.get(note, self.offsets_ms[instrument]) / 1000

    def to_dict(self) -> dict:
        data = asdict(self)
        data["note_offsets_ms"] = {str(k): v for k, v in self.note_offsets_ms.items()}
        return data

    @classmethod
    def from_dict(cls, data: dict) -> Calibration:
        return cls(
            offsets_ms=dict(data["offsets_ms"]),
            note_offsets_ms={int(k): v for k, v in data["note_offsets_ms"].items()},
            std_ms=dict(data["std_ms"]),
            counts=dict(data["counts"]),
            outliers=int(data["outliers"]),
        )


def _envelope(audio: np.ndarray, sr: int) -> np.ndarray:
    mono = audio.mean(axis=0).astype(np.float64)
    window = max(2, int(ENVELOPE_MS / 1000 * sr))
    energy = np.concatenate([[0.0], np.cumsum(mono**2)])
    rms = np.zeros(len(mono))
    half = window // 2
    centers = np.arange(half, len(mono) - (window - half))
    rms[centers] = np.sqrt(
        np.maximum(0.0, (energy[centers + window - half] - energy[centers - half]) / window)
    )
    return rms


def _onset_near(env: np.ndarray, sr: int, midi_time: float) -> float | None:
    """Onset (s) of the single hit around a MIDI note, or None if there is no clear hit."""
    a = int((midi_time - SEARCH_BEFORE_MS / 1000) * sr)
    b = int((midi_time + SEARCH_AFTER_MS / 1000) * sr)
    base_n = int(BASELINE_MS / 1000 * sr)
    if a - base_n < 0 or b > len(env):
        return None
    segment = env[a:b]
    peak_idx = int(np.argmax(segment))
    peak = segment[peak_idx]
    base = float(np.median(env[a - base_n : a]))
    if peak < 10 * max(base, 1e-6):
        return None
    level = base + ONSET_FRACTION * (peak - base)
    below = np.flatnonzero(segment[:peak_idx] < level)
    if len(below) == 0:  # already loud at the start of the window: not isolated
        return None
    return (a + below[-1] + 1) / sr


def measure_calibration(
    audio: np.ndarray, sr: int, notes: list[dict], note_map: NoteMap
) -> Calibration:
    notes, _ = drop_double_triggers(notes, note_map)
    times = np.array([n["time_sec"] for n in notes], dtype=np.float64)
    order = np.argsort(times)
    env = _envelope(audio, sr)

    per_note: dict[int, list[float]] = {}
    for rank, i in enumerate(order):
        note = notes[i]
        if note_map.instrument_for(note["note"]) is None:
            continue
        before = times[order[rank - 1]] if rank > 0 else -np.inf
        after = times[order[rank + 1]] if rank + 1 < len(order) else np.inf
        if times[i] - before < ISOLATION_BEFORE_SEC or after - times[i] < ISOLATION_AFTER_SEC:
            continue
        onset = _onset_near(env, sr, times[i])
        if onset is not None:
            per_note.setdefault(note["note"], []).append((onset - times[i]) * 1000)

    offsets, stds, counts, note_offsets, outliers = {}, {}, {}, {}, 0
    for instrument in EVALUATED_INSTRUMENTS:
        inlier_deltas, deviations = [], []
        for note, raw in per_note.items():
            if note_map.instrument_for(note) != instrument:
                continue
            deltas = np.array(raw)
            center = np.median(deltas)
            inliers = deltas[np.abs(deltas - center) <= OUTLIER_MS]
            outliers += len(deltas) - len(inliers)
            if len(inliers) >= MIN_HITS:
                note_offsets[note] = round(float(np.median(inliers)), 3)
            inlier_deltas.extend(inliers)
            deviations.extend(inliers - np.median(inliers))  # spread around each pad's latency
        if len(inlier_deltas) < MIN_HITS:
            raise CalibrationError(
                f"{instrument}: only {len(inlier_deltas)} clean hits (need {MIN_HITS}); "
                "hit the pad alone, about 1 s apart"
            )
        offsets[instrument] = round(float(np.median(inlier_deltas)), 3)
        stds[instrument] = round(float(np.std(deviations)), 3)
        counts[instrument] = len(inlier_deltas)

    worst = max(stds, key=stds.get)
    if stds[worst] > MAX_STD_MS:
        raise CalibrationError(
            f"{worst}: latency std {stds[worst]:.2f} ms exceeds {MAX_STD_MS} ms (SC-008)"
        )
    return Calibration(offsets, note_offsets, stds, counts, outliers)
