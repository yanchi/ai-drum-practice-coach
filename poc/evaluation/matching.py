"""One-to-one matching of estimated drum events to ground truth and the metrics (research R-11)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from poc.domain import EVALUATED_INSTRUMENTS, DrumEvent, GroundTruth, InstrumentMetrics

MIN_TP_FOR_SPEARMAN = 5


@dataclass(frozen=True)
class EventsEvaluation:
    metrics: dict[str, InstrumentMetrics]
    ghost_notes: dict[str, dict[str, int]]  # instrument -> {"detected", "total"}
    tp_errors_ms: dict[str, list[float]]  # estimate - truth for each TP (for pooling)


def _in_regions(t: float, regions: list[tuple[float, float]]) -> bool:
    return any(a <= t <= b for a, b in regions)


def _assign(truth: np.ndarray, estimates: np.ndarray, tolerance: float) -> list[tuple[int, int]]:
    """Maximum number of (truth, estimate) pairs within the tolerance, then minimum total
    time difference. Pairs outside the tolerance are never matched."""
    if len(truth) == 0 or len(estimates) == 0:
        return []
    from scipy.optimize import linear_sum_assignment

    diff = np.abs(truth[:, None] - estimates[None, :])
    allowed = diff <= tolerance
    # A forbidden pair costs more than any sum of allowed pairs, so the solver first
    # maximizes the number of allowed pairs and then minimizes their total distance.
    cost = np.where(allowed, diff, tolerance * (len(truth) + len(estimates) + 1))
    rows, cols = linear_sum_assignment(cost)
    return [(r, c) for r, c in zip(rows, cols, strict=True) if allowed[r, c]]


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _spearman(strengths: list[float], velocities: list[int | None]) -> float | None:
    if len(strengths) < MIN_TP_FOR_SPEARMAN or any(v is None for v in velocities):
        return None
    if len(set(strengths)) < 2 or len(set(velocities)) < 2:  # undefined for constant input
        return None
    from scipy.stats import spearmanr

    value = spearmanr(strengths, velocities).statistic
    return None if np.isnan(value) else round(float(value), 4)


def evaluate_events(
    groundtruth: GroundTruth, events: list[DrumEvent], tolerance_ms: float = 50.0
) -> EventsEvaluation:
    tolerance = tolerance_ms / 1000
    metrics, ghosts, errors = {}, {}, {}
    for instrument in EVALUATED_INSTRUMENTS:
        hits = [h for h in groundtruth.hits if h.instrument == instrument]
        estimates = [
            e
            for e in events
            if e.instrument == instrument and _in_regions(e.time_sec, groundtruth.regions)
        ]
        pairs = _assign(
            np.array([h.time_sec for h in hits]),
            np.array([e.time_sec for e in estimates]),
            tolerance,
        )
        matched_hits = {r for r, _ in pairs}
        tp_pairs = [(r, c) for r, c in pairs if not hits[r].ghost]
        ghost_detected = sum(1 for r, _ in pairs if hits[r].ghost)

        tp = len(tp_pairs)
        fn = sum(1 for i, h in enumerate(hits) if not h.ghost and i not in matched_hits)
        fp = len(estimates) - len(pairs)  # an estimate matched to a ghost note is not an FP
        precision, recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
        f1 = _ratio(2 * tp, 2 * tp + fp + fn)

        deltas = [(estimates[c].time_sec - hits[r].time_sec) * 1000 for r, c in tp_pairs]
        abs_d = np.abs(deltas)
        timing = {
            "mae": round(float(abs_d.mean()), 3) if tp else None,
            "median_abs": round(float(np.median(abs_d)), 3) if tp else None,
            "p95_abs": round(float(np.percentile(abs_d, 95)), 3) if tp else None,
            "median_signed": round(float(np.median(deltas)), 3) if tp else None,
        }
        metrics[instrument] = InstrumentMetrics(
            tp=tp,
            fp=fp,
            fn=fn,
            precision=precision,
            recall=recall,
            f1=f1,
            timing_ms=timing,
            strength_spearman=_spearman(
                [estimates[c].strength for _, c in tp_pairs],
                [hits[r].velocity for r, _ in tp_pairs],
            ),
        )
        ghosts[instrument] = {"detected": ghost_detected, "total": sum(h.ghost for h in hits)}
        errors[instrument] = [round(d, 3) for d in deltas]
    return EventsEvaluation(metrics, ghosts, errors)
