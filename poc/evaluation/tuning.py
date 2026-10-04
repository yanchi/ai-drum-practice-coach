"""`poc tune-thresholds`: choose per-instrument detection thresholds with TD-17 ground truth,
using leave-one-song-out so the reported F1 is not tuned on the song it is measured on
(research R-16)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from poc.domain import EVALUATED_INSTRUMENTS, GroundTruth
from poc.errors import UserInputError
from poc.evaluation.matching import evaluate_events

GRID = tuple(round(x, 2) for x in np.arange(0.06, 0.301, 0.02))


@dataclass(frozen=True)
class Song:
    """One evaluated song: model activations of its drum stem and the ground truth."""

    key: str
    activations: np.ndarray
    groundtruth: GroundTruth


def _counts(songs: list[Song], instrument: str, threshold: float, events_fn) -> np.ndarray:
    """Pooled (tp, fp, fn) for one instrument at one threshold."""
    total = np.zeros(3, dtype=int)
    for song in songs:
        events = events_fn(song.activations, {instrument: threshold})
        m = evaluate_events(song.groundtruth, events).metrics[instrument]
        total += (m.tp, m.fp, m.fn)
    return total


def _f1(tp: int, fp: int, fn: int) -> float:
    return 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.0


def _best(grid, counts: dict) -> float:
    """Threshold with the highest F1; among ties, the middle one (robust to small shifts)."""
    scores = {t: _f1(*counts[t]) for t in grid}
    top = max(scores.values())
    tied = [t for t in grid if scores[t] >= top - 1e-9]
    return tied[len(tied) // 2]


def tune(songs: list[Song], events_fn, grid=GRID) -> dict:
    """For each instrument: pooled P / R / F1 per threshold over all songs, and the
    leave-one-out F1 (threshold chosen on the other songs, scored on the held-out one)."""
    if len(songs) < 2:
        raise UserInputError("need TD-17 evaluations of at least 2 songs to tune thresholds")
    report = {}
    for instrument in EVALUATED_INSTRUMENTS:
        # counts[song][threshold] = (tp, fp, fn)
        counts = {s.key: {t: _counts([s], instrument, t, events_fn) for t in grid} for s in songs}
        pooled = {t: sum(counts[s.key][t] for s in songs) for t in grid}
        best_all = _best(grid, pooled)

        folds, held_out = [], np.zeros(3, dtype=int)
        for song in songs:
            train = {t: sum(counts[s.key][t] for s in songs if s.key != song.key) for t in grid}
            chosen = _best(grid, train)
            held_out += counts[song.key][chosen]
            folds.append({"held_out": song.key, "threshold": chosen})
        tp, fp, fn = (int(x) for x in held_out)
        report[instrument] = {
            "grid": [
                {
                    "threshold": t,
                    "precision": round(pooled[t][0] / max(1, pooled[t][0] + pooled[t][1]), 4),
                    "recall": round(pooled[t][0] / max(1, pooled[t][0] + pooled[t][2]), 4),
                    "f1": round(_f1(*pooled[t]), 4),
                }
                for t in grid
            ],
            "best_threshold_all_songs": best_all,
            "folds": folds,
            "leave_one_out": {"tp": tp, "fp": fp, "fn": fn, "f1": round(_f1(tp, fp, fn), 4)},
        }
    return report


def load_songs(evaluations_dir: Path, recordings_dir: Path, activations_fn) -> list[Song]:
    """TD-17 evaluations (latest per song) with the drum stem activations recomputed once."""
    latest: dict[str, dict] = {}
    for path in sorted(Path(evaluations_dir).glob("*/evaluation.json")):
        data = json.loads(path.read_text())
        if data["groundtruth"]["source"] == "td17_midi" and "drum_stem" in data["results"]:
            latest[data["poc1_run_id"]] = data
    songs = []
    for run_id, data in sorted(latest.items()):
        gt_path = Path(recordings_dir) / data["groundtruth"]["target_id"] / "groundtruth.json"
        tx_id = data["results"]["drum_stem"]["transcription_id"]
        tx_path = Path(evaluations_dir).parent / "transcriptions" / tx_id / "transcription.json"
        if not gt_path.exists() or not tx_path.exists():
            raise UserInputError(
                f"missing groundtruth or transcription for {data['evaluation_id']}"
            )
        audio = Path(json.loads(tx_path.read_text())["input"]["audio_path"])
        songs.append(
            Song(
                key=run_id,
                activations=activations_fn(audio),
                groundtruth=GroundTruth.from_dict(json.loads(gt_path.read_text())),
            )
        )
    return songs


def report_markdown(report: dict) -> str:
    lines = ["# PoC 2 Threshold Tuning", ""]
    for instrument, r in report.items():
        loo = r["leave_one_out"]
        lines += [
            f"## {instrument}",
            "",
            f"- Leave-one-out F1: **{loo['f1']:.3f}** "
            f"(TP {loo['tp']} / FP {loo['fp']} / FN {loo['fn']})",
            f"- Chosen per fold: {', '.join(str(f['threshold']) for f in r['folds'])}",
            f"- Best on all songs: {r['best_threshold_all_songs']}",
            "",
            "| threshold | precision | recall | F1 |",
            "|---|---|---|---|",
            *(
                f"| {g['threshold']:.2f} | {g['precision']:.3f} "
                f"| {g['recall']:.3f} | {g['f1']:.3f} |"
                for g in r["grid"]
            ),
            "",
        ]
    return "\n".join(lines)
