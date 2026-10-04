"""`poc summarize-beats` / `poc check-beats` (specs/003-beat-bar-mapping SC-001〜SC-009)."""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any

from poc.beat.run import load_beatgrid

ADOPTED = "regularized_offset"  # the variant poc map uses
VARIANTS = ("raw", "regularized", ADOPTED)
TARGETS = {"beat_f": 0.95, "downbeat_f": 0.90, "bpm_pct": 2.0, "mapping": 0.95, "jitter_ms": 20.0}
SONGS = 5
FOUR_MINUTES = 240.0
TIME_LIMIT_SEC = 120.0


def _latest(evaluations: list[dict], kind: str, source: str) -> list[dict]:
    latest: dict[str, dict] = {}
    for data in sorted(evaluations, key=lambda d: d["evaluation_id"]):
        if data["beatgrid"]["input_kind"] == kind and data["groundtruth"]["source"] == source:
            latest[data["poc1_run_id"]] = data
    return list(latest.values())


def _variant(data: dict, name: str) -> dict:
    return next(v for v in data["variants"] if v["name"] == name)


def _pooled_f(evaluations: list[dict], name: str, key: str) -> float | None:
    tp = fp = fn = 0
    for data in evaluations:
        m = _variant(data, name)[key]
        tp, fp, fn = tp + m["tp"], fp + m["fp"], fn + m["fn"]
    return round(2 * tp / (2 * tp + fp + fn), 4) if tp + fp + fn else None


def _pooled_mapping(evaluations: list[dict], name: str) -> float | None:
    events = sum(_variant(d, name)["mapping"]["events"] for d in evaluations)
    correct = sum(_variant(d, name)["mapping"]["matched_grid"] for d in evaluations)
    return round(correct / events, 4) if events else None


def _fmt(value: Any, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def summarize_beats(evaluations_dir: Path, report_dir: Path) -> str:
    evaluations = [
        json.loads(p.read_text()) for p in sorted(Path(evaluations_dir).glob("*/evaluation.json"))
    ]
    taps = _latest(evaluations, "mix", "td17_taps")
    stem = _latest(evaluations, "drum_stem", "td17_taps")
    jitters = [
        d["tap_jitter_ms"]
        for d in taps
        if d.get("tap_jitter_ms", {}) and d["tap_jitter_ms"].get("count")
    ]
    enough = len(taps) >= SONGS

    def status(ok: bool | None) -> str:
        if ok is None:
            return "N/A"
        if not enough:
            return "INSUFFICIENT" if ok else "FAIL"
        return "PASS" if ok else "FAIL"

    beat_f = _pooled_f(taps, ADOPTED, "beats")
    down_f = _pooled_f(taps, ADOPTED, "downbeats")
    bpm_errors = [_variant(d, ADOPTED)["bpm_error_pct"] for d in taps]
    meters = [_variant(d, ADOPTED)["meter_match"] for d in taps]
    mapping = _pooled_mapping(taps, ADOPTED)
    jitter = max((j["median_abs"] for j in jitters), default=None)
    times = [
        d["beatgrid"]["timings_sec"]["total"] * FOUR_MINUTES / d["beatgrid"]["duration_sec"]
        for d in taps
        if d["beatgrid"].get("timings_sec") and d["beatgrid"].get("duration_sec")
    ]
    complete = sum(bool(d["beatgrid"].get("complete")) for d in taps)

    rows = [
        (
            "SC-001 Beat F-measure",
            f"≥ {TARGETS['beat_f']}",
            _fmt(beat_f),
            status(None if beat_f is None else beat_f >= TARGETS["beat_f"]),
        ),
        (
            "SC-002 Downbeat F-measure",
            f"≥ {TARGETS['downbeat_f']}",
            _fmt(down_f),
            status(None if down_f is None else down_f >= TARGETS["downbeat_f"]),
        ),
        (
            "SC-003 BPM error / meter",
            f"≤ {TARGETS['bpm_pct']}% / all match",
            f"max {_fmt(max(bpm_errors, default=None), 2)}% / {sum(bool(m) for m in meters)}"
            f"/{len(meters)}",
            status(
                None
                if not taps
                else all(e is not None and e <= TARGETS["bpm_pct"] for e in bpm_errors)
                and all(meters)
            ),
        ),
        (
            "SC-004 Mapping accuracy",
            f"≥ {TARGETS['mapping']}",
            _fmt(mapping),
            status(None if mapping is None else mapping >= TARGETS["mapping"]),
        ),
        (
            "SC-005 Songs with taps / tap jitter",
            f"{SONGS} songs, median ≤ {TARGETS['jitter_ms']:.0f} ms",
            f"{len(taps)} songs, jitter {_fmt(jitter, 1)} ms ({len(jitters)} songs)",
            "PASS"
            if enough and jitters and jitter <= TARGETS["jitter_ms"]
            else ("FAIL" if jitters and jitter > TARGETS["jitter_ms"] else "INSUFFICIENT"),
        ),
        (
            "SC-006 4-min song beats + grid",
            f"≤ {TIME_LIMIT_SEC:.0f} s",
            f"{_fmt(max(times, default=None), 1)} s (normalized)",
            "N/A" if not times else ("PASS" if max(times) <= TIME_LIMIT_SEC else "FAIL"),
        ),
        (
            "SC-008 Beat grid records complete",
            "all",
            f"{complete}/{len(taps)}",
            "N/A" if not taps else ("PASS" if complete == len(taps) else "FAIL"),
        ),
    ]
    lines = [
        f"# PoC 3 Beat / Bar Mapping Summary ({date.today().isoformat()})",
        "",
        f"Songs with tapped ground truth: {len(taps)} / with manual beats for tap jitter: "
        f"{len(jitters)}",
        "",
        "| Criterion | Target | Result | Status |",
        "|---|---|---|---|",
        *[f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows],
        "",
        "## Variants (mix input, pooled)",
        "",
        "| Variant | Beat F | Downbeat F | Mapping accuracy |",
        "|---|---|---|---|",
        *[
            f"| {name} | {_fmt(_pooled_f(taps, name, 'beats'))} | "
            f"{_fmt(_pooled_f(taps, name, 'downbeats'))} | {_fmt(_pooled_mapping(taps, name))} |"
            for name in VARIANTS
        ],
        "",
        "## Mix vs drum stem input (regularized + offset)",
        "",
        "| Input | Songs | Beat F | Downbeat F | Mapping accuracy |",
        "|---|---|---|---|---|",
        *[
            f"| {label} | {len(group)} | {_fmt(_pooled_f(group, ADOPTED, 'beats'))} | "
            f"{_fmt(_pooled_f(group, ADOPTED, 'downbeats'))} | "
            f"{_fmt(_pooled_mapping(group, ADOPTED))} |"
            for label, group in (("mix", taps), ("drum stem", stem))
        ],
        "",
        "SC-007 is checked with `poc check-beats`, SC-009 with the developer's time log.",
        "",
    ]
    markdown = "\n".join(lines)
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "poc3_summary.md").write_text(markdown)
    _write_csv(report_dir / "poc3_summary.csv", taps + stem)
    return markdown


def _write_csv(path: Path, evaluations: list[dict]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "evaluation_id",
                "poc1_run_id",
                "input",
                "variant",
                "beat_f",
                "downbeat_f",
                "bpm_error_pct",
                "meter_match",
                "mapping_accuracy",
                "tap_jitter_median_ms",
            ]
        )
        for d in evaluations:
            jitter = (d.get("tap_jitter_ms") or {}).get("median_abs")
            for v in d["variants"]:
                writer.writerow(
                    [
                        d["evaluation_id"],
                        d["poc1_run_id"],
                        d["beatgrid"]["input_kind"],
                        v["name"],
                        v["beats"]["f_measure"],
                        v["downbeats"]["f_measure"],
                        v["bpm_error_pct"],
                        v["meter_match"],
                        v["mapping"]["accuracy"],
                        jitter,
                    ]
                )


def compare_beatgrids(dir_a: Path, dir_b: Path) -> tuple[int, int, float, bool]:
    """(beats a, beats b, max difference in seconds, identical) of two BeatGrids."""
    a, b = load_beatgrid(dir_a), load_beatgrid(dir_b)
    ta, tb = a.beat_times, b.beat_times
    same_len = len(ta) == len(tb) and len(a.downbeats) == len(b.downbeats)
    diff = (
        max(
            [abs(x - y) for x, y in zip(ta + a.downbeats, tb + b.downbeats, strict=True)], default=0
        )
        if same_len
        else float("inf")
    )
    return len(ta), len(tb), diff, same_len and diff == 0
