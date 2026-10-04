"""Beat ground truth from beats tapped on the TD-17 (specs/003-beat-bar-mapping R-06).

The developer taps the hi-hat (hand or pedal) on every beat of the original song and adds the
kick on downbeats. Times are corrected with the calibration like the PoC 2 ground truth."""

from __future__ import annotations

import numpy as np

from poc.domain import BeatGroundTruth, RunWarning
from poc.recording.calibration import Calibration
from poc.recording.note_map import NoteMap, drop_double_triggers

DOWNBEAT_KICK_SEC = 0.05  # a kick this close to a hi-hat tap marks a downbeat
LOCAL_INTERVALS = 8
TAP_TOLERANCE = 0.35  # an interval this far off the local median is reported
STRAY_FACTOR = 2.0  # a first / last tap this many median intervals away from the rest is stray


def taps_to_groundtruth(
    notes: list[dict],
    note_map: NoteMap,
    calibration: Calibration,
    calibration_id: str,
    shift_sec: float,
    poc1_run_id: str,
    duration_sec: float,
) -> BeatGroundTruth:
    """`notes` are MIDI note-ons on the recording timeline; `shift_sec` is the count-in plus
    the stream latency, so song time = MIDI time + pad offset - shift_sec."""
    kept, dropped = drop_double_triggers(notes, note_map)
    taps: dict[str, list[float]] = {"hihat": [], "kick": []}
    offsets_used = {}
    for note in kept:
        instrument = note_map.instrument_for(note["note"])
        if instrument not in taps:
            continue
        offset = calibration.offset_sec(note["note"], instrument)
        offsets_used[note["note"]] = round(offset * 1000, 3)
        t = note["time_sec"] + offset - shift_sec
        if 0 <= t < duration_sec:
            taps[instrument].append(round(t, 6))
    beats, stray = trim_stray_taps(sorted(taps["hihat"]))
    kicks = np.array(sorted(taps["kick"]))
    downbeats = [t for t in beats if len(kicks) and np.min(np.abs(kicks - t)) <= DOWNBEAT_KICK_SEC]
    return BeatGroundTruth(
        source="td17_taps",
        poc1_run_id=poc1_run_id,
        regions=[(beats[0], beats[-1])] if beats else [],
        beats=beats,
        downbeats=downbeats,
        alignment={
            "calibration_id": calibration_id,
            "note_offsets_ms": {str(k): v for k, v in offsets_used.items()},
            "max_std_ms": max(calibration.std_ms.values()),
            "dropped_double_triggers": dropped,
            "shift_sec": round(shift_sec, 6),
        },
        warnings=[
            RunWarning(
                code="stray_tap",
                message=f"stray tap at {t:.2f} s left out of the ground truth",
                value=round(t, 3),
            )
            for t in stray
        ]
        + tap_warnings(beats),
    )


def trim_stray_taps(beats: list[float]) -> tuple[list[float], list[float]]:
    """Drop taps at either end that are far from the steady tapping (e.g. a hit during the
    count-in). Returns (kept beats, dropped taps)."""
    if len(beats) < 4:
        return beats, []
    median = float(np.median(np.diff(beats)))
    start, end = 0, len(beats)
    while end - start > 3 and beats[start + 1] - beats[start] > STRAY_FACTOR * median:
        start += 1
    while end - start > 3 and beats[end - 1] - beats[end - 2] > STRAY_FACTOR * median:
        end -= 1
    return beats[start:end], beats[:start] + beats[end:]


def tap_warnings(beats: list[float]) -> list[RunWarning]:
    """Intervals far from the median of the surrounding intervals (a missed or extra tap)."""
    if len(beats) < 3:
        return []
    diffs = np.diff(beats)
    half = LOCAL_INTERVALS // 2
    warnings = []
    for i, d in enumerate(diffs):
        local = float(np.median(np.delete(diffs[max(0, i - half) : i + half + 1], min(i, half))))
        if abs(d - local) > TAP_TOLERANCE * local:
            warnings.append(
                RunWarning(
                    code="tap_interval",
                    message=f"tap interval {d * 1000:.0f} ms at {beats[i]:.2f} s "
                    f"(around {local * 1000:.0f} ms)",
                    value=round(beats[i], 3),
                )
            )
    return warnings
