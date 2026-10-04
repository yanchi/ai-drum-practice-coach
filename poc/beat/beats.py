"""Beat / downbeat positions of a PoC 1 song with Beat This! (docs/poc-plan.md).

The song is rebuilt as drums.wav + accompaniment.wav of the PoC 1 run, so the beat times
share the timeline of the accompaniment played back by `poc record`. Results are cached in
<run>/beats.json. Beat This! objects stay inside this module."""

from __future__ import annotations

import json
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

import numpy as np
import soundfile as sf

from poc.errors import UserInputError

BEATS_FILE = "beats.json"
CHECKPOINT = "final0"


def _load_song(poc1_run_dir: Path) -> tuple[np.ndarray, int]:
    """Mono drums + accompaniment of the run, shape (samples,)."""
    parts = []
    for name in ("drums.wav", "accompaniment.wav"):
        path = poc1_run_dir / name
        if not path.exists():
            raise UserInputError(f"{name} not found in {poc1_run_dir}")
        audio, sr = sf.read(path, dtype="float32", always_2d=True)
        parts.append((audio.mean(axis=1), sr))
    (drums, sr), (accompaniment, sr_acc) = parts
    if sr != sr_acc:
        raise UserInputError(f"{poc1_run_dir}: drums.wav and accompaniment.wav sample rates differ")
    length = min(len(drums), len(accompaniment))
    return drums[:length] + accompaniment[:length], sr


def detect_beats(signal: np.ndarray, sr: int) -> tuple[list[float], list[float]]:
    """Beat and downbeat times in seconds (Beat This! with minimal post-processing)."""
    from beat_this.inference import Audio2Beats

    beats, downbeats = Audio2Beats(checkpoint_path=CHECKPOINT, device="cpu")(signal, sr)
    return [round(float(t), 4) for t in beats], [round(float(t), 4) for t in downbeats]


def fill_beat_gaps(
    beats: list[float], max_missing: int = 3, tolerance: float = 0.15
) -> list[float]:
    """Insert evenly spaced beats where the tracker skipped 1 to `max_missing` beats.

    A gap is filled when it is close (within `tolerance` of the median interval per beat)
    to a whole number of median intervals. Longer gaps (e.g. a section without drums) stay."""
    if len(beats) < 3:
        return list(beats)
    median = float(np.median(np.diff(beats)))
    out = [beats[0]]
    for t in beats[1:]:
        gap = t - out[-1]
        k = int(round(gap / median))
        if 2 <= k <= max_missing + 1 and abs(gap / k - median) < tolerance * median:
            start = out[-1]
            out += [round(start + gap * j / k, 4) for j in range(1, k)]
        out.append(t)
    return out


def load_or_detect_beats(poc1_run_dir: Path) -> dict:
    """The run's beats.json, created on first use."""
    poc1_run_dir = Path(poc1_run_dir)
    path = poc1_run_dir / BEATS_FILE
    if path.exists():
        return json.loads(path.read_text())
    signal, sr = _load_song(poc1_run_dir)
    beats, downbeats = detect_beats(signal, sr)
    if len(beats) < 2:
        raise UserInputError(f"{poc1_run_dir}: Beat This! found fewer than two beats")
    intervals = np.diff(beats)
    data = {
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "input": "drums.wav + accompaniment.wav",
        "model": {"method": "beat_this", "version": version("beat-this"), "checkpoint": CHECKPOINT},
        "bpm_median": round(60.0 / float(np.median(intervals)), 2),
        "beats": beats,
        "downbeats": downbeats,
    }
    path.write_text(json.dumps(data, indent=1) + "\n")
    return data


def drum_offset_sec(beats: list[float], onsets: list[float], window: float = 0.06) -> float | None:
    """Median of (onset - nearest beat) over the onsets within `window` of a beat.

    Beat This! places beats on a 20 ms frame grid and tends to lag the drum onsets, so the
    click is shifted by this offset to sound with the original drums."""
    if len(beats) < 2 or not onsets:
        return None
    b = np.asarray(beats)
    t = np.asarray(onsets)
    i = np.clip(np.searchsorted(b, t), 1, len(b) - 1)
    nearest = np.where(np.abs(b[i] - t) < np.abs(b[i - 1] - t), b[i], b[i - 1])
    diff = t - nearest
    diff = diff[np.abs(diff) <= window]
    return round(float(np.median(diff)), 4) if len(diff) else None


def latest_drum_stem_onsets(poc1_run_id: str, transcriptions_dir: Path) -> tuple[str, list[float]]:
    """Kick / snare times of the newest drum stem transcription of the run (`poc transcribe`)."""
    candidates = []
    for path in Path(transcriptions_dir).glob("*/transcription.json"):
        data = json.loads(path.read_text())
        source = data.get("input", {})
        if source.get("kind") == "drum_stem" and source.get("poc1_run_id") == poc1_run_id:
            candidates.append((data["created_at"], data))
    if not candidates:
        raise UserInputError(
            f"no drum stem transcription of {poc1_run_id} in {transcriptions_dir}; "
            "run `poc transcribe` first"
        )
    data = max(candidates, key=lambda c: c[0])[1]
    onsets = [e["time_sec"] for e in data["events"] if e["instrument"] in ("kick", "snare")]
    return data["transcription_id"], onsets


def click_beats(
    poc1_run_dir: Path, transcriptions_dir: Path
) -> tuple[list[float], list[float], dict]:
    """Beats and downbeats for the play-along click: gaps filled and shifted onto the
    original drums. Returns (beats, downbeats, a record of what was done)."""
    poc1_run_dir = Path(poc1_run_dir)
    detected = load_or_detect_beats(poc1_run_dir)
    beats = fill_beat_gaps(detected["beats"])
    transcription_id, onsets = latest_drum_stem_onsets(poc1_run_dir.name, transcriptions_dir)
    offset = drum_offset_sec(beats, onsets) or 0.0
    info = {
        "beats_file": BEATS_FILE,
        "filled_beats": len(beats) - len(detected["beats"]),
        "offset_ms": round(offset * 1000, 1),
        "offset_from": transcription_id,
    }
    beats = [round(t + offset, 4) for t in beats]
    downbeats = [round(t + offset, 4) for t in detected["downbeats"]]
    return beats, downbeats, info
