"""Manual annotation of a commercial song (research R-13): annotation.yaml + hits.csv."""

from __future__ import annotations

import csv
from pathlib import Path

import yaml

from poc.domain import GroundTruth, GroundTruthHit
from poc.errors import UserInputError

LABELS = {"k": "kick", "s": "snare", "h": "hihat"}


def load_annotation(annotation_yaml: Path, runs_dir: Path = Path("output/runs")) -> GroundTruth:
    """Hits marked with labels k / s / h (snare ghost notes: sg) inside the given regions.
    "hg" is accepted and scored as a normal hi-hat hit."""
    annotation_yaml = Path(annotation_yaml)
    data = yaml.safe_load(annotation_yaml.read_text()) or {}
    run_id = str(data.get("poc1_run_id", ""))
    if not (Path(runs_dir) / run_id / "run.json").exists():
        raise UserInputError(f"{annotation_yaml}: PoC 1 run {run_id!r} not found in {runs_dir}")

    try:
        regions = sorted((float(a), float(b)) for a, b in data.get("regions") or [])
    except (TypeError, ValueError):
        raise UserInputError(f"{annotation_yaml}: regions must be [[start, end], ...]") from None
    if not regions:
        raise UserInputError(f"{annotation_yaml}: no regions")
    for (a, b), following in zip(regions, regions[1:] + [None], strict=True):
        if not a < b:
            raise UserInputError(f"{annotation_yaml}: invalid region [{a}, {b}]")
        if following and following[0] < b:
            raise UserInputError(f"{annotation_yaml}: regions overlap at {following[0]}")

    hits_path = annotation_yaml.parent / str(data.get("hits_csv", "hits.csv"))
    hits = []
    with hits_path.open(newline="") as f:
        for line_no, row in enumerate(csv.reader(f), start=1):
            if not row or not "".join(row).strip():
                continue
            if line_no == 1 and row[0].strip().lower() in ("time", "time_sec"):
                continue
            label = row[1].strip().lower() if len(row) > 1 else ""
            ghost = label.endswith("g") and len(label) == 2
            instrument = LABELS.get(label[0] if ghost else label)
            try:
                time_sec = float(row[0])
            except ValueError:
                instrument = None
            if instrument is None:
                raise UserInputError(
                    f"{hits_path}: line {line_no}: expected 'time,label' with label "
                    f"k / s / h (ghost: sg / hg), got {row!r}"
                )
            if any(a <= time_sec <= b for a, b in regions):
                # Only snare ghost notes are kept apart; "hg" counts as a normal hi-hat hit.
                is_ghost = ghost and instrument == "snare"
                hits.append(GroundTruthHit(time_sec, instrument, None, is_ghost))
    return GroundTruth(
        source="manual",
        target_kind="poc1_song",
        target_id=run_id,
        regions=regions,
        hits=sorted(hits, key=lambda h: h.time_sec),
    )
