"""`poc evaluate-beats`: compare a BeatGrid with beat ground truth (specs/003-beat-bar-mapping
R-08). Three variants of the same estimate are scored: raw (as estimated, no alignment),
regularized (downbeats regularized, no alignment) and regularized_offset (as saved)."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from poc.beat.run import load_beatgrid
from poc.domain import BeatGrid, BeatGroundTruth, BeatMetrics
from poc.errors import PocError, UserInputError
from poc.evaluation.beat_groundtruth import BEATS_CSV, load_beat_annotation
from poc.evaluation.matching import _assign
from poc.mapping.reference import position_of


def _inside(times: list[float], regions: list[tuple[float, float]], margin: float = 0.0):
    return np.array([t for t in times if any(a - margin <= t <= b + margin for a, b in regions)])


def _ratio(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def match_times(
    truth: list[float], estimate: list[float], regions: list[tuple[float, float]], tolerance: float
) -> BeatMetrics:
    """One-to-one matching inside the regions. Estimates within `tolerance` outside a region
    edge may still match a truth at the edge."""
    t = _inside(truth, regions)
    e = _inside(estimate, regions, margin=tolerance)
    pairs = _assign(t, e, tolerance)
    used = {c for _, c in pairs}
    # estimates outside the regions only count when they matched an edge beat
    outside = sum(
        1 for i, x in enumerate(e) if i not in used and not any(a <= x <= b for a, b in regions)
    )
    tp, fn = len(pairs), len(t) - len(pairs)
    fp = len(e) - len(pairs) - outside
    errors = np.array([(e[c] - t[r]) * 1000 for r, c in pairs])
    precision, recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    f = (
        round(2 * precision * recall / (precision + recall), 4)
        if precision and recall
        else (0.0 if t.size or e.size else None)
    )
    timing = (
        {
            "median_abs": round(float(np.median(np.abs(errors))), 2),
            "p95_abs": round(float(np.percentile(np.abs(errors), 95)), 2),
            "median_signed": round(float(np.median(errors)), 2),
        }
        if len(errors)
        else {"median_abs": None, "p95_abs": None, "median_signed": None}
    )
    return BeatMetrics(tp, fp, fn, precision, recall, f, timing)


def _meter(beats: list[float], downbeats: list[float]) -> int | None:
    if len(downbeats) < 2:
        return None
    index = np.searchsorted(beats, np.asarray(downbeats) - 1e-3)
    counts = [int(c) for c in np.diff(index) if c > 0]
    return Counter(counts).most_common(1)[0][0] if counts else None


def evaluate_grid(
    beats: list[float],
    downbeats: list[float],
    bpm: float,
    meter: int,
    groundtruth: BeatGroundTruth,
    tolerance_ms: float = 70.0,
) -> dict[str, Any]:
    tol = tolerance_ms / 1000
    gt_beats = _inside(groundtruth.beats, groundtruth.regions)
    true_bpm = 60.0 / float(np.median(np.diff(gt_beats))) if len(gt_beats) > 1 else None
    true_meter = _meter(groundtruth.beats, groundtruth.downbeats)
    return {
        "beats": match_times(groundtruth.beats, beats, groundtruth.regions, tol),
        "downbeats": match_times(groundtruth.downbeats, downbeats, groundtruth.regions, tol),
        "bpm_true": round(true_bpm, 2) if true_bpm else None,
        "bpm_error_pct": round(abs(bpm - true_bpm) / true_bpm * 100, 3) if true_bpm else None,
        "meter_true": true_meter,
        "meter_match": None if true_meter is None else meter == true_meter,
    }


def mapping_accuracy(
    event_times: list[float],
    beats: list[float],
    downbeats: list[float],
    groundtruth: BeatGroundTruth,
    tolerance_ms: float = 70.0,
) -> dict[str, Any]:
    """Share of events (inside the regions) that land in the same bar (same bar start within
    the tolerance, so bar numbering does not matter), the same beat and the same grid
    position with the estimated grid as with the ground-truth grid."""
    tol = tolerance_ms / 1000
    events = _inside(event_times, groundtruth.regions)
    counts = {"events": int(len(events)), "matched_bar": 0, "matched_beat": 0, "matched_grid": 0}
    correct = 0
    for t in events:
        est = position_of(float(t), beats, downbeats)
        true = position_of(float(t), groundtruth.beats, groundtruth.downbeats)
        if not est.bar or not true.bar:  # unmapped or before the first downbeat
            continue
        bar_ok = abs(downbeats[est.bar - 1] - groundtruth.downbeats[true.bar - 1]) <= tol
        beat_ok = bar_ok and est.beat == true.beat
        grid_ok = beat_ok and est.grid == true.grid
        counts["matched_bar"] += bar_ok
        counts["matched_beat"] += beat_ok
        counts["matched_grid"] += grid_ok
        correct += grid_ok
    counts["accuracy"] = _ratio(correct, len(events))
    return counts


def tap_jitter(
    taps: list[float], manual: BeatGroundTruth, tolerance_ms: float = 70.0
) -> dict[str, Any]:
    """Differences between tapped beats and beats marked by hand, inside the manual regions."""
    tol = tolerance_ms / 1000
    m = _inside(manual.beats, manual.regions)
    t = _inside(taps, manual.regions, margin=tol)
    pairs = _assign(m, t, tol)
    diffs = np.array([(t[c] - m[r]) * 1000 for r, c in pairs])
    if not len(diffs):
        return {"count": 0, "median_abs": None, "p95_abs": None, "median_signed": None}
    return {
        "count": len(diffs),
        "median_abs": round(float(np.median(np.abs(diffs))), 2),
        "p95_abs": round(float(np.percentile(np.abs(diffs), 95)), 2),
        "median_signed": round(float(np.median(diffs)), 2),
    }


def variants(grid: BeatGrid) -> dict[str, tuple[list[float], list[float]]]:
    """(beats, downbeats) of the three variants, rebuilt from the saved grid."""
    shift = grid.offset.get("applied_ms", 0.0) / 1000
    beats = grid.beat_times
    unshift = [round(t - shift, 4) for t in beats]
    raw = [round(t - shift, 4) for t in grid.downbeats_raw]
    regularized = [round(t - shift, 4) for t in grid.downbeats]
    return {
        "raw": (unshift, raw),
        "regularized": (unshift, regularized),
        "regularized_offset": (beats, grid.downbeats),
    }


def _latest_transcription_events(run_id: str, transcriptions_dir: Path) -> tuple[str, list[float]]:
    candidates = []
    for path in Path(transcriptions_dir).glob("*/transcription.json"):
        data = json.loads(path.read_text())
        if data["input"].get("kind") == "drum_stem" and data["input"].get("poc1_run_id") == run_id:
            candidates.append(data)
    if not candidates:
        raise UserInputError(f"no drum stem transcription of {run_id}; run `poc transcribe` first")
    data = max(candidates, key=lambda d: d["created_at"])
    return data["transcription_id"], [e["time_sec"] for e in data["events"]]


def _manual_for(run_id: str, annotations_dir: Path) -> BeatGroundTruth | None:
    for path in sorted(Path(annotations_dir).glob("*/annotation.yaml")):
        if (path.parent / BEATS_CSV).exists():
            try:
                gt = load_beat_annotation(path)
            except UserInputError:
                continue
            if gt.poc1_run_id == run_id:
                return gt
    return None


def run_evaluate_beats(
    beatgrid_dir: Path,
    output_dir: Path,
    *,
    taps_dir: Path | None = None,
    annotation: Path | None = None,
    transcription_dir: Path | None = None,
    transcriptions_dir: Path = Path("output/transcriptions"),
    annotations_dir: Path = Path("data/annotations"),
    tolerance_ms: float = 70.0,
    now: datetime | None = None,
) -> Path:
    grid = load_beatgrid(beatgrid_dir)
    run_id = grid.input["poc1_run_id"]
    if (taps_dir is None) == (annotation is None):
        raise UserInputError("give either --taps or --annotation")
    if taps_dir is not None:
        path = Path(taps_dir) / "beat_groundtruth.json"
        if not path.exists():
            raise UserInputError(f"beat_groundtruth.json not found in {taps_dir}")
        groundtruth = BeatGroundTruth.from_dict(json.loads(path.read_text()))
        gt_info = {"source": groundtruth.source, "recording_id": Path(taps_dir).name}
    else:
        groundtruth = load_beat_annotation(annotation)
        gt_info = {"source": groundtruth.source, "annotation": str(annotation)}
    if groundtruth.poc1_run_id != run_id:
        raise UserInputError(f"ground truth is for {groundtruth.poc1_run_id}, grid for {run_id}")
    gt_info["regions"] = [list(r) for r in groundtruth.regions]

    if transcription_dir is not None:
        data = json.loads((Path(transcription_dir) / "transcription.json").read_text())
        transcription_id, event_times = (
            data["transcription_id"],
            [e["time_sec"] for e in data["events"]],
        )
    else:
        transcription_id, event_times = _latest_transcription_events(run_id, transcriptions_dir)

    results = []
    for name, (beats, downbeats) in variants(grid).items():
        result = evaluate_grid(beats, downbeats, grid.bpm, grid.meter, groundtruth, tolerance_ms)
        result["beats"] = result["beats"].to_dict()
        result["downbeats"] = result["downbeats"].to_dict()
        result["mapping"] = mapping_accuracy(
            event_times, beats, downbeats, groundtruth, tolerance_ms
        )
        results.append({"name": name, **result})

    jitter = None
    if groundtruth.source == "td17_taps":
        manual = _manual_for(run_id, annotations_dir)
        if manual is not None:
            jitter = tap_jitter(groundtruth.beats, manual, tolerance_ms)

    now = now or datetime.now().astimezone()
    evaluation_id = f"{now:%Y%m%d-%H%M%S}_{grid.beatgrid_id}"
    complete = all(
        [grid.input, grid.estimator, grid.timings_sec, grid.peak_memory, grid.environment]
    )
    data = {
        "schema_version": 1,
        "evaluation_id": evaluation_id,
        "created_at": now.isoformat(timespec="seconds"),
        "poc1_run_id": run_id,
        "beatgrid": {
            "beatgrid_id": grid.beatgrid_id,
            "input_kind": grid.input["kind"],
            "duration_sec": grid.input.get("duration_sec"),
            "timings_sec": grid.timings_sec,
            "complete": complete,
        },
        "transcription_id": transcription_id,
        "groundtruth": gt_info,
        "tolerance_ms": tolerance_ms,
        "variants": results,
        "tap_jitter_ms": jitter,
    }
    output_dir = Path(output_dir)
    final_dir = output_dir / evaluation_id
    partial_dir = output_dir / f"{evaluation_id}.partial"
    if final_dir.exists() or partial_dir.exists():
        raise PocError(f"evaluation directory already exists: {final_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    partial_dir.mkdir()
    try:
        (partial_dir / "evaluation.json").write_text(json.dumps(data, indent=2) + "\n")
        partial_dir.rename(final_dir)
    except BaseException:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise
    return final_dir
