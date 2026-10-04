"""`poc transcribe` / `poc check-events`: drum events from a PoC 1 run (US1, US3, FR-015)."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import soundfile as sf

from poc.audio.decode import load_song
from poc.domain import (
    RunWarning,
    TranscriptionInput,
    TranscriptionInputKind,
    TranscriptionRun,
)
from poc.errors import PocError, UserInputError
from poc.evaluation.metrics import Stopwatch, environment_info, peak_rss_bytes
from poc.transcription.base import Transcriber
from poc.transcription.render import render_check_wav, write_events_midi

# Formats the transcriber can read directly; others (e.g. m4a) are decoded with ffmpeg first.
DIRECT_FORMATS = {".wav", ".flac", ".aif", ".aiff"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_poc1_run(poc1_run_dir: Path) -> dict[str, Any]:
    path = Path(poc1_run_dir) / "run.json"
    if not path.exists():
        raise UserInputError(f"not a PoC 1 run directory (run.json not found): {poc1_run_dir}")
    return json.loads(path.read_text())


def resolve_input(poc1_run_dir: Path, kind: TranscriptionInputKind) -> Path:
    run = load_poc1_run(poc1_run_dir)
    paths = {
        "drum_stem": Path(poc1_run_dir) / "drums.wav",
        "accompaniment": Path(poc1_run_dir) / "accompaniment.wav",
        "mix": Path(run["song"]["path"]),
    }
    path = paths[kind]
    if not path.exists():
        raise UserInputError(f"{kind} audio not found: {path}")
    return path


def run_transcription(
    poc1_run_dir: Path,
    kind: TranscriptionInputKind,
    output_dir: Path,
    transcriber: Transcriber,
    *,
    now: datetime | None = None,
) -> Path:
    """Transcribe one input of a PoC 1 run and save the result. Returns the output directory."""
    poc1_run_dir = Path(poc1_run_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run = load_poc1_run(poc1_run_dir)
    audio_path = resolve_input(poc1_run_dir, kind)
    watch = Stopwatch()

    with watch.stage("load"):
        song, original, _ = load_song(Path(run["song"]["path"]))
        audio_sha = _sha256(audio_path)

    with tempfile.TemporaryDirectory() as tmp, watch.stage("transcribe"):
        source = audio_path
        if audio_path.suffix.lower() not in DIRECT_FORMATS:
            decoded_song, decoded, _ = load_song(audio_path)
            source = Path(tmp) / "input.wav"
            sf.write(source, decoded.T, decoded_song.sample_rate, subtype="FLOAT")
        events, info = transcriber.transcribe(source)
    events = sorted(events, key=lambda e: e.time_sec)

    now = now or datetime.now().astimezone()
    # The kind keeps the drum stem and the mix of one run apart even within the same second.
    transcription_id = f"{now:%Y%m%d-%H%M%S}_{kind}_{audio_sha[:8]}"
    final_dir = output_dir / transcription_id
    partial_dir = output_dir / f"{transcription_id}.partial"
    if final_dir.exists() or partial_dir.exists():
        raise PocError(f"transcription directory already exists: {final_dir}")
    partial_dir.mkdir()
    try:
        with watch.stage("write"):
            write_events_midi(events, partial_dir / "events.mid")
            check = render_check_wav(original, song.sample_rate, events)
            sf.write(partial_dir / "check.wav", check.T, song.sample_rate, subtype="FLOAT")
        warnings = []
        if not events:
            warnings.append(RunWarning(code="no_events", message="no drum events were found"))
        result = TranscriptionRun(
            transcription_id=transcription_id,
            created_at=now.isoformat(timespec="seconds"),
            input=TranscriptionInput(
                kind=kind,
                poc1_run_id=run["run_id"],
                audio_path=str(audio_path.resolve()),
                audio_sha256=audio_sha,
                duration_sec=song.duration_sec,
            ),
            transcriber=info,
            events=events,
            warnings=warnings,
            timings_sec=watch.result(),
            peak_memory={"rss_bytes": peak_rss_bytes()},
            environment=environment_info(),
        )
        (partial_dir / "transcription.json").write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n"
        )
        partial_dir.rename(final_dir)
    except BaseException:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise
    return final_dir


def _load_transcription(directory: Path) -> dict[str, Any]:
    path = Path(directory) / "transcription.json"
    if not path.exists():
        raise UserInputError(f"transcription.json not found in {directory}")
    return json.loads(path.read_text())


def compare_transcriptions(dir_a: Path, dir_b: Path) -> tuple[int, int, int, bool]:
    """Return (events in a, events in b, mismatches, passed) for SC-005.

    Both must share the input audio and transcriber settings (the device may differ).
    """
    a, b = _load_transcription(dir_a), _load_transcription(dir_b)
    if a["input"]["audio_sha256"] != b["input"]["audio_sha256"]:
        raise UserInputError("the two transcriptions have different inputs (audio_sha256)")

    def settings(t: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in t["transcriber"].items() if k != "device"}

    if settings(a) != settings(b):
        raise UserInputError("the two transcriptions used different transcriber settings")

    def key(e: dict[str, Any]) -> tuple[float, str, float]:
        return (e["time_sec"], e["instrument"], e["strength"])

    events_a = Counter(key(e) for e in a["events"])
    events_b = Counter(key(e) for e in b["events"])
    mismatches = max(sum((events_a - events_b).values()), sum((events_b - events_a).values()))
    return len(a["events"]), len(b["events"]), mismatches, mismatches == 0
