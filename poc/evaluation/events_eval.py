"""`poc evaluate`: drum events against TD-17 or manual ground truth (US2, US3, FR-015)."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from poc.domain import EVALUATED_INSTRUMENTS, DrumEvent, GroundTruth
from poc.errors import PocError, UserInputError
from poc.evaluation.groundtruth import load_annotation
from poc.evaluation.matching import EventsEvaluation, evaluate_events
from poc.evaluation.run import run_separation
from poc.recording.mix import build_evaluation_mix, load_calibration
from poc.recording.note_map import load_note_map
from poc.separation.base import Separator
from poc.transcription.base import Transcriber
from poc.transcription.run import run_transcription

SCHEMA_VERSION = 1


def _events(transcription_dir: Path) -> list[DrumEvent]:
    data = json.loads((transcription_dir / "transcription.json").read_text())
    return [DrumEvent(**e) for e in data["events"]]


def _result(transcription_dir: Path, evaluation: EventsEvaluation) -> dict[str, Any]:
    return {
        "transcription_id": transcription_dir.name,
        "metrics": {k: m.to_dict() for k, m in evaluation.metrics.items()},
        "tp_errors_ms": evaluation.tp_errors_ms,
        "ghost_notes": evaluation.ghost_notes,
    }


def _write(evaluations_dir: Path, evaluation_id: str, data: dict[str, Any]) -> Path:
    evaluations_dir = Path(evaluations_dir)
    evaluations_dir.mkdir(parents=True, exist_ok=True)
    final_dir = evaluations_dir / evaluation_id
    partial_dir = evaluations_dir / f"{evaluation_id}.partial"
    if final_dir.exists() or partial_dir.exists():
        raise PocError(f"evaluation directory already exists: {final_dir}")
    partial_dir.mkdir()
    try:
        (partial_dir / "evaluation.json").write_text(json.dumps(data, indent=1) + "\n")
        partial_dir.rename(final_dir)
    except BaseException:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise
    return final_dir


def _groundtruth_summary(gt: GroundTruth) -> dict[str, Any]:
    return {
        "source": gt.source,
        "target_kind": gt.target_kind,
        "target_id": gt.target_id,
        "regions": [list(r) for r in gt.regions],
        "hit_counts": dict(Counter(h.instrument for h in gt.hits if not h.ghost)),
        "ghost_counts": dict(Counter(h.instrument for h in gt.hits if h.ghost)),
        "alignment": gt.alignment.to_dict() if gt.alignment else None,
    }


def evaluate_recording(
    recording_dir: Path,
    *,
    separator: Separator,
    transcriber: Transcriber,
    runs_dir: Path = Path("output/runs"),
    eval_runs_dir: Path = Path("output/eval_runs"),
    transcriptions_dir: Path = Path("output/transcriptions"),
    evaluations_dir: Path = Path("output/evaluations"),
    calibrations_dir: Path = Path("output/recordings/calibrations"),
    calibration_dir: Path | None = None,
    tolerance_ms: float = 50.0,
    ghost_velocity: int = 40,
    inputs: tuple[str, ...] = ("drum_stem", "mix"),
    now: datetime | None = None,
) -> Path:
    """Evaluate one TD-17 play-along. Returns the evaluation directory."""
    recording_dir = Path(recording_dir)
    path = recording_dir / "recording.json"
    if not path.exists():
        raise UserInputError(f"recording.json not found in {recording_dir}")
    recording = json.loads(path.read_text())
    if recording.get("kind", "play_along") != "play_along":
        raise UserInputError(f"{recording_dir} is not a play-along recording")
    poc1_run_dir = Path(runs_dir) / recording["poc1_run_id"]
    if not (poc1_run_dir / "run.json").exists():
        raise UserInputError(f"PoC 1 run {recording['poc1_run_id']} not found in {runs_dir}")

    calibration_id, calibration = load_calibration(calibrations_dir, calibration_dir)
    mix_path, gt = build_evaluation_mix(
        recording_dir, poc1_run_dir, calibration_id, calibration, load_note_map(), ghost_velocity
    )
    mix_run = run_separation(mix_path, eval_runs_dir, separator)

    results = {}
    for kind in inputs:
        tx = run_transcription(mix_run, kind, transcriptions_dir, transcriber)
        results[kind] = _result(tx, evaluate_events(gt, _events(tx), tolerance_ms))

    # Hits found in the original accompaniment alone: leftovers of the original drums (FR-015).
    residual_tx = run_transcription(poc1_run_dir, "accompaniment", transcriptions_dir, transcriber)
    residual = Counter(
        e.instrument
        for e in _events(residual_tx)
        if e.instrument in EVALUATED_INSTRUMENTS
        and any(a <= e.time_sec <= b for a, b in gt.regions)
    )

    now = now or datetime.now().astimezone()
    data = {
        "schema_version": SCHEMA_VERSION,
        "evaluation_id": f"{now:%Y%m%d-%H%M%S}_{recording['recording_id']}",
        "created_at": now.isoformat(timespec="seconds"),
        "poc1_run_id": recording["poc1_run_id"],
        "groundtruth": _groundtruth_summary(gt),
        "tolerance_ms": tolerance_ms,
        "results": results,
        "residual_drum_hits": {
            "transcription_id": residual_tx.name,
            "counts": {i: residual.get(i, 0) for i in EVALUATED_INSTRUMENTS},
        },
    }
    return _write(evaluations_dir, data["evaluation_id"], data)


def evaluate_annotation(
    annotation_yaml: Path,
    *,
    transcriber: Transcriber,
    runs_dir: Path = Path("output/runs"),
    transcriptions_dir: Path = Path("output/transcriptions"),
    evaluations_dir: Path = Path("output/evaluations"),
    tolerance_ms: float = 50.0,
    inputs: tuple[str, ...] = ("drum_stem", "mix"),
    now: datetime | None = None,
) -> Path:
    """Evaluate a PoC 1 run against a manual annotation. Returns the evaluation directory."""
    gt = load_annotation(annotation_yaml, runs_dir)
    poc1_run_dir = Path(runs_dir) / gt.target_id
    results = {}
    for kind in inputs:
        tx = run_transcription(poc1_run_dir, kind, transcriptions_dir, transcriber)
        results[kind] = _result(tx, evaluate_events(gt, _events(tx), tolerance_ms))
    now = now or datetime.now().astimezone()
    data = {
        "schema_version": SCHEMA_VERSION,
        "evaluation_id": f"{now:%Y%m%d-%H%M%S}_manual_{gt.target_id}",
        "created_at": now.isoformat(timespec="seconds"),
        "poc1_run_id": gt.target_id,
        "groundtruth": _groundtruth_summary(gt),
        "tolerance_ms": tolerance_ms,
        "results": results,
        "residual_drum_hits": None,
    }
    return _write(evaluations_dir, data["evaluation_id"], data)
