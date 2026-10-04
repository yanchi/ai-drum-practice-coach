"""Beats for the play-along click of `poc record --click` (PoC 2 research R-18).

The song is rebuilt as drums.wav + accompaniment.wav of the PoC 1 run, so the beat times
share the timeline of the accompaniment played back by `poc record`. Results are cached in
<run>/beats.json. PoC 3 builds its BeatGrid with poc/beat/run.py instead."""

from __future__ import annotations

import json
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

import numpy as np
import soundfile as sf

from poc.beat.beat_this_adapter import CHECKPOINT, detect_beats
from poc.beat.grid import drum_offset_sec, fill_beat_gaps
from poc.errors import UserInputError

BEATS_FILE = "beats.json"


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
