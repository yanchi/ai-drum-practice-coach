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
