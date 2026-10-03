"""`poc summarize-events`: aggregate PoC 2 evaluations and judge the success criteria."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from poc.domain import EVALUATED_INSTRUMENTS
from poc.errors import UserInputError

MIN_F1 = 0.80  # SC-001
MAX_MEDIAN_MS = 10.0  # SC-002
MAX_P95_MS = 30.0  # SC-002
MIN_TD17_SONGS = 5  # SC-003
MIN_MANUAL_SONGS = 1  # SC-003
MAX_SEC_FOR_4MIN = 120.0  # SC-004
MAX_CALIBRATION_STD_MS = 1.0  # SC-008
MAX_F1_DROP = 0.10  # SC-009
REQUIRED_TRANSCRIPTION_FIELDS = (
    ("input", "audio_sha256"),
    ("transcriber", "method"),
    ("transcriber", "version"),
    ("transcriber", "params"),
    ("timings_sec",),
    ("peak_memory",),
    ("environment",),
    ("warnings",),
)


@dataclass(frozen=True)
class Criterion:
    criterion: str
    label: str
    target: str
    result: str
    status: str  # PASS / FAIL / INSUFFICIENT / N/A


def _latest_per_song(evaluations: list[dict], source: str) -> list[dict]:
    latest: dict[str, dict] = {}
    for data in sorted(evaluations, key=lambda d: d["evaluation_id"]):
        if data["groundtruth"]["source"] == source:
            latest[data["poc1_run_id"]] = data
    return list(latest.values())


def pooled(evaluations: list[dict], kind: str) -> dict[str, dict[str, Any]]:
    """Per instrument: summed TP / FP / FN, F1 and timing over all TP errors."""
    out = {}
    for inst in EVALUATED_INSTRUMENTS:
        tp = fp = fn = 0
        errors: list[float] = []
        for data in evaluations:
            result = data["results"].get(kind)
            if result is None:
                continue
            m = result["metrics"][inst]
            tp, fp, fn = tp + m["tp"], fp + m["fp"], fn + m["fn"]
            errors += result["tp_errors_ms"][inst]
        abs_e = np.abs(errors)
        out[inst] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else None,
            "median_abs_ms": float(np.median(abs_e)) if errors else None,
            "p95_abs_ms": float(np.percentile(abs_e, 95)) if errors else None,
            "median_signed_ms": float(np.median(errors)) if errors else None,
        }
    return out


def _fmt(value: float | None, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _has(data: dict, keys: tuple[str, ...]) -> bool:
    for key in keys:
        if not isinstance(data, dict) or data.get(key) is None:
            return False
        data = data[key]
    return True


def summarize_events(
    evaluations_dir: Path, report_dir: Path, today: date | None = None
) -> tuple[list[Criterion], str]:
    evaluations_dir = Path(evaluations_dir)
    evaluations = [
        json.loads(p.read_text()) for p in sorted(evaluations_dir.glob("*/evaluation.json"))
    ]
    if not evaluations:
        raise UserInputError(f"no evaluations in {evaluations_dir}")
    td17 = _latest_per_song(evaluations, "td17_midi")
    manual = _latest_per_song(evaluations, "manual")
    stem = pooled(td17, "drum_stem")
    mix = pooled(td17, "mix")
    criteria: list[Criterion] = []

    if td17:
        f1s = {i: stem[i]["f1"] for i in EVALUATED_INSTRUMENTS}
        ok = all(v is not None and v >= MIN_F1 for v in f1s.values())
        result = " / ".join(f"{i} {_fmt(v)}" for i, v in f1s.items())
        criteria.append(
            Criterion(
                "SC-001", "F1 (TD-17, drum stem)", f"≥ {MIN_F1}", result, "PASS" if ok else "FAIL"
            )
        )
        timing_ok = all(
            stem[i]["median_abs_ms"] is not None
            and stem[i]["median_abs_ms"] <= MAX_MEDIAN_MS
            and stem[i]["p95_abs_ms"] <= MAX_P95_MS
            for i in EVALUATED_INSTRUMENTS
        )
        result = " / ".join(
            f"{i} {_fmt(stem[i]['median_abs_ms'], 1)}/{_fmt(stem[i]['p95_abs_ms'], 1)}"
            for i in EVALUATED_INSTRUMENTS
        )
        criteria.append(
            Criterion(
                "SC-002",
                "Timing median/p95 ms",
                f"≤ {MAX_MEDIAN_MS:g} / ≤ {MAX_P95_MS:g}",
                result,
                "PASS" if timing_ok else "FAIL",
            )
        )
    else:
        criteria.append(
            Criterion(
                "SC-001", "F1 (TD-17, drum stem)", f"≥ {MIN_F1}", "no TD-17 evaluation", "N/A"
            )
        )
        criteria.append(
            Criterion("SC-002", "Timing median/p95 ms", "≤ 10 / ≤ 30", "no TD-17 evaluation", "N/A")
        )

    enough = len(td17) >= MIN_TD17_SONGS and len(manual) >= MIN_MANUAL_SONGS
    criteria.append(
        Criterion(
            "SC-003",
            "Evaluated songs",
            f"TD-17 ≥ {MIN_TD17_SONGS}, manual ≥ {MIN_MANUAL_SONGS}",
            f"TD-17 {len(td17)}, manual {len(manual)}",
            "PASS" if enough else "INSUFFICIENT",
        )
    )

    transcriptions = []
    for data in td17 + manual:
        for result in data["results"].values():
            path = (
                evaluations_dir.parent
                / "transcriptions"
                / result["transcription_id"]
                / "transcription.json"
            )
            if path.exists():
                transcriptions.append(json.loads(path.read_text()))
    stem_times = [
        t["timings_sec"]["total"] / t["input"]["duration_sec"] * 240
        for t in transcriptions
        if t["input"]["kind"] == "drum_stem" and t.get("timings_sec")
    ]
    if stem_times:
        worst = max(stem_times)
        criteria.append(
            Criterion(
                "SC-004",
                "4-min song transcription",
                f"≤ {MAX_SEC_FOR_4MIN:g} s",
                f"{worst:.1f} s (normalized)",
                "PASS" if worst <= MAX_SEC_FOR_4MIN else "FAIL",
            )
        )
    else:
        criteria.append(
            Criterion("SC-004", "4-min song transcription", "≤ 120 s", "not recorded", "N/A")
        )

    complete = sum(
        all(_has(t, keys) for keys in REQUIRED_TRANSCRIPTION_FIELDS) for t in transcriptions
    )
    criteria.append(
        Criterion(
            "SC-006",
            "Transcription records complete",
            "all",
            f"{complete}/{len(transcriptions)}",
            "PASS" if transcriptions and complete == len(transcriptions) else "FAIL",
        )
    )

    stds = [
        d["groundtruth"]["alignment"]["max_std_ms"]
        for d in td17
        if d["groundtruth"].get("alignment")
    ]
    if stds:
        criteria.append(
            Criterion(
                "SC-008",
                "Calibration std",
                f"≤ {MAX_CALIBRATION_STD_MS:g} ms",
                f"max {max(stds):.2f} ms",
                "PASS" if max(stds) <= MAX_CALIBRATION_STD_MS else "FAIL",
            )
        )
    else:
        criteria.append(
            Criterion("SC-008", "Calibration std", "≤ 1 ms", "no TD-17 evaluation", "N/A")
        )

    if td17 and manual:
        man = pooled(manual, "drum_stem")
        drops = {i: (stem[i]["f1"] or 0) - (man[i]["f1"] or 0) for i in EVALUATED_INSTRUMENTS}
        ok = all(d <= MAX_F1_DROP for d in drops.values())
        result = " / ".join(
            f"{i} {_fmt(man[i]['f1'])} (Δ{-drops[i]:+.3f})" for i in EVALUATED_INSTRUMENTS
        )
        criteria.append(
            Criterion(
                "SC-009",
                "Manual F1 (reference)",
                f"drop ≤ {MAX_F1_DROP}",
                result,
                "PASS" if ok else "FAIL",
            )
        )
    else:
        criteria.append(
            Criterion(
                "SC-009", "Manual F1 (reference)", "drop ≤ 0.10", "needs TD-17 and manual", "N/A"
            )
        )

    markdown = _markdown(criteria, td17, manual, stem, mix, today or date.today())
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "poc2_summary.md").write_text(markdown)
    _write_csv(report_dir / "poc2_summary.csv", td17 + manual)
    return criteria, markdown


def _markdown(criteria, td17, manual, stem, mix, today) -> str:
    lines = [
        f"# PoC 2 Evaluation Summary ({today.isoformat()})",
        "",
        f"TD-17 songs: {len(td17)} / manual songs: {len(manual)}",
        "",
        "| Criterion | Target | Result | Status |",
        "|---|---|---|---|",
        *(f"| {c.criterion} {c.label} | {c.target} | {c.result} | {c.status} |" for c in criteria),
        "",
        "## TD-17: drum stem vs mix (US3)",
        "",
        "| Instrument | F1 stem | F1 mix | P stem | R stem | median signed ms |",
        "|---|---|---|---|---|---|",
        *(
            f"| {i} | {_fmt(stem[i]['f1'])} | {_fmt(mix[i]['f1'])} | {_fmt(stem[i]['precision'])} "
            f"| {_fmt(stem[i]['recall'])} | {_fmt(stem[i]['median_signed_ms'], 1)} |"
            for i in EVALUATED_INSTRUMENTS
        ),
        "",
    ]
    residual = {
        i: sum(d["residual_drum_hits"]["counts"][i] for d in td17) for i in EVALUATED_INSTRUMENTS
    }
    ghosts = {
        i: (
            sum(d["results"]["drum_stem"]["ghost_notes"][i]["detected"] for d in td17),
            sum(d["results"]["drum_stem"]["ghost_notes"][i]["total"] for d in td17),
        )
        for i in EVALUATED_INSTRUMENTS
    }
    lines += [
        "Residual original drums in the accompaniment (detections inside the regions): "
        + ", ".join(f"{i} {residual[i]}" for i in EVALUATED_INSTRUMENTS),
        "",
        "Ghost notes detected: " + ", ".join(f"{i} {d}/{t}" for i, (d, t) in ghosts.items()),
        "",
        "SC-005 is checked with `poc check-events`, SC-007 with the developer's time log.",
        "",
    ]
    return "\n".join(lines)


def _write_csv(path: Path, evaluations: list[dict]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "evaluation_id",
                "source",
                "poc1_run_id",
                "input",
                "instrument",
                "tp",
                "fp",
                "fn",
                "precision",
                "recall",
                "f1",
                "median_abs_ms",
                "p95_abs_ms",
                "strength_spearman",
            ]
        )
        for data in evaluations:
            for kind, result in data["results"].items():
                for inst, m in result["metrics"].items():
                    writer.writerow(
                        [
                            data["evaluation_id"],
                            data["groundtruth"]["source"],
                            data["poc1_run_id"],
                            kind,
                            inst,
                            m["tp"],
                            m["fp"],
                            m["fn"],
                            m["precision"],
                            m["recall"],
                            m["f1"],
                            m["timing_ms"]["median_abs"],
                            m["timing_ms"]["p95_abs"],
                            m["strength_spearman"],
                        ]
                    )
