"""`poc summarize`: aggregate evaluation sheets and judge SC-001, SC-002, SC-004, SC-005, SC-007."""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from poc.domain import ISSUE_CHOICES, SCHEMA_VERSION, SeparationEvaluation
from poc.errors import UserInputError
from poc.evaluation.sheet import load_sheet

MIN_SONGS = 5  # SC-001
MAX_LAG_MS = 1.0  # SC-004
MAX_SEC_FOR_4MIN = 600.0  # SC-005
REFERENCE_SONG_SEC = 240.0

# FR-010 items that must be present in every run.json (SC-007).
REQUIRED_RUN_FIELDS = (
    ("song", "sha256"),
    ("separator", "method"),
    ("separator", "version"),
    ("separator", "params"),
    ("stems",),
    ("timings_sec",),
    ("peak_memory",),
    ("environment",),
    ("warnings",),
)


@dataclass(frozen=True)
class SongRow:
    run_id: str
    song_label: str
    genre: str
    verdict: str
    issues: str  # ";"-separated
    alignment_lag_ms: float
    total_sec: float | None
    peak_rss_mb: float | None
    device: str


@dataclass(frozen=True)
class Criterion:
    criterion: str  # e.g. "SC-002"
    label: str
    target: str
    result: str
    status: str  # PASS / FAIL / INSUFFICIENT / N/A


@dataclass(frozen=True)
class SummaryResult:
    rows: list[SongRow]
    criteria: list[Criterion]
    incomplete: list[str]
    markdown: str


Evaluated = tuple[dict[str, Any], SeparationEvaluation, SongRow]


def _has_field(run: dict[str, Any], keys: tuple[str, ...]) -> bool:
    value: Any = run
    for key in keys:
        if not isinstance(value, dict) or value.get(key) is None:
            return False
        value = value[key]
    return True


def _normalized_sec(run: dict[str, Any]) -> float | None:
    total = (run.get("timings_sec") or {}).get("total")
    duration = run["song"].get("duration_sec")
    if total is None or not duration:
        return None
    return total / duration * REFERENCE_SONG_SEC


def _load_runs(runs_dir: Path) -> list[dict[str, Any]]:
    runs = []
    for run_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        path = run_dir / "run.json"
        if run_dir.name.endswith(".partial") or not path.exists():
            continue
        run = json.loads(path.read_text())
        if run.get("schema_version") != SCHEMA_VERSION:
            raise UserInputError(
                f"{path}: unsupported schema_version {run.get('schema_version')!r}"
            )
        run["_dir"] = run_dir
        runs.append(run)
    return runs


def _judge(evaluated: list[Evaluated], all_runs: list[dict[str, Any]]) -> list[Criterion]:
    rows = [row for _, _, row in evaluated]
    songs = {run["song"]["sha256"] for run, _, _ in evaluated}
    enough = len(songs) >= MIN_SONGS
    criteria = [
        Criterion(
            "SC-001",
            "Generation success",
            f"100% of ≥{MIN_SONGS} songs",
            f"{len(songs)} songs evaluated",
            "PASS" if enough else "INSUFFICIENT",
        )
    ]

    ng = [r.song_label for r in rows if r.verdict == "ng"]
    if ng:
        sc002 = "FAIL"
    else:
        sc002 = "PASS" if enough else "INSUFFICIENT"
    result = f"{len(rows) - len(ng)}/{len(rows)} OK"
    if ng:
        result += f" (NG: {', '.join(ng)})"
    criteria.append(Criterion("SC-002", "Developer verdict", "OK in every song", result, sc002))

    max_lag = max(abs(r.alignment_lag_ms) for r in rows)
    aligned = all(run["alignment"].get("passed") for run, _, _ in evaluated)
    criteria.append(
        Criterion(
            "SC-004",
            "Alignment",
            f"≤ {MAX_LAG_MS:g} ms in all songs",
            f"max {max_lag:.2f} ms",
            "PASS" if aligned and max_lag <= MAX_LAG_MS else "FAIL",
        )
    )

    normalized = [s for run, _, _ in evaluated if (s := _normalized_sec(run)) is not None]
    if normalized:
        worst = max(normalized)
        criteria.append(
            Criterion(
                "SC-005",
                "4-min song time",
                f"≤ {MAX_SEC_FOR_4MIN / 60:g} min",
                f"{worst / 60:.1f} min (normalized)",
                "PASS" if worst <= MAX_SEC_FOR_4MIN else "FAIL",
            )
        )
    else:
        criteria.append(Criterion("SC-005", "4-min song time", "≤ 10 min", "not recorded", "N/A"))

    missing = [
        run["run_id"]
        for run in all_runs
        if not all(_has_field(run, keys) for keys in REQUIRED_RUN_FIELDS)
    ]
    criteria.append(
        Criterion(
            "SC-007",
            "Run records complete",
            "all FR-010 items in every run",
            f"{len(all_runs) - len(missing)}/{len(all_runs)} complete",
            "PASS" if not missing else "FAIL",
        )
    )
    return criteria


def _markdown(criteria: list[Criterion], evaluated: list[Evaluated], today: date) -> str:
    rows = [row for _, _, row in evaluated]
    genres = ", ".join(sorted({r.genre for r in rows if r.genre})) or "-"
    issues = Counter(i for _, sheet, _ in evaluated for i in sheet.issues)
    issue_text = ", ".join(f"{i} {issues[i]}" for i in ISSUE_CHOICES if issues[i]) or "none"
    lines = [
        f"# PoC 1 Evaluation Summary ({today.isoformat()})",
        "",
        f"Evaluated songs: {len(rows)} (genres: {genres})",
        "",
        "| Criterion | Target | Result | Status |",
        "|---|---|---|---|",
        *(f"| {c.criterion} {c.label} | {c.target} | {c.result} | {c.status} |" for c in criteria),
        "",
        f"Issues noted: {issue_text}",
        "",
        "SC-006 (reproducibility) is checked separately with `poc check-repro`.",
        "",
    ]
    return "\n".join(lines)


def summarize(runs_dir: Path, report_dir: Path, today: date | None = None) -> SummaryResult:
    runs_dir, report_dir = Path(runs_dir), Path(report_dir)
    if not runs_dir.is_dir():
        raise UserInputError(f"runs directory not found: {runs_dir}")

    all_runs = _load_runs(runs_dir)
    evaluated: list[Evaluated] = []
    incomplete: list[str] = []
    for run in all_runs:
        sheet_path = run["_dir"] / "evaluation.yaml"
        sheet = load_sheet(sheet_path) if sheet_path.exists() else None
        if sheet is None:
            incomplete.append(run["run_id"])
            continue
        rss = (run.get("peak_memory") or {}).get("rss_bytes")
        row = SongRow(
            run_id=run["run_id"],
            song_label=sheet.song_label,
            genre=sheet.genre,
            verdict=sheet.verdict,
            issues=";".join(sheet.issues),
            alignment_lag_ms=run["alignment"]["lag_ms"],
            total_sec=(run.get("timings_sec") or {}).get("total"),
            peak_rss_mb=rss / 1024**2 if rss is not None else None,
            device=run["separator"].get("device", ""),
        )
        evaluated.append((run, sheet, row))

    if not evaluated:
        pending = ", ".join(incomplete) or "none"
        raise UserInputError(
            f"no completed evaluation sheets in {runs_dir} (not filled in: {pending})"
        )

    criteria = _judge(evaluated, all_runs)
    markdown = _markdown(criteria, evaluated, today or date.today())

    report_dir.mkdir(parents=True, exist_ok=True)
    rows = [row for _, _, row in evaluated]
    with (report_dir / "summary.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0])))
        writer.writeheader()
        writer.writerows(asdict(r) for r in rows)
    (report_dir / "summary.md").write_text(markdown)

    return SummaryResult(rows=rows, criteria=criteria, incomplete=incomplete, markdown=markdown)
