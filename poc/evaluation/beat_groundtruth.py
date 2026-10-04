"""Beats marked by hand with `poc annotate --beats` (specs/003-beat-bar-mapping R-07):
annotation.yaml (`beat_regions`) + beats.csv (`time_sec,label`, label b / d)."""

from __future__ import annotations

import csv
from pathlib import Path

import yaml

from poc.domain import BeatGroundTruth
from poc.errors import UserInputError

BEAT_LABELS = {"b", "d"}  # beat, downbeat
BEATS_CSV = "beats.csv"


def load_beat_annotation(annotation_yaml: Path) -> BeatGroundTruth:
    annotation_yaml = Path(annotation_yaml)
    data = yaml.safe_load(annotation_yaml.read_text()) or {}
    try:
        regions = sorted((float(a), float(b)) for a, b in data.get("beat_regions") or [])
    except (TypeError, ValueError):
        raise UserInputError(
            f"{annotation_yaml}: beat_regions must be [[start, end], ...]"
        ) from None
    if not regions:
        raise UserInputError(f"{annotation_yaml}: no beat_regions")
    path = annotation_yaml.parent / BEATS_CSV
    if not path.exists():
        raise UserInputError(f"{path} not found; mark beats with `poc annotate --beats`")
    beats, downbeats = [], []
    with path.open(newline="") as f:
        for line_no, row in enumerate(csv.reader(f), start=1):
            if not row or (line_no == 1 and row[0].strip().lower().startswith("time")):
                continue
            label = row[1].strip().lower() if len(row) > 1 else ""
            try:
                t = float(row[0])
            except ValueError:
                t = None
            if t is None or label not in BEAT_LABELS:
                raise UserInputError(f"{path}: line {line_no}: expected 'time,b' or 'time,d'")
            if any(a <= t <= b for a, b in regions):
                beats.append(t)
                if label == "d":
                    downbeats.append(t)
    return BeatGroundTruth(
        source="manual",
        poc1_run_id=str(data.get("poc1_run_id", "")),
        regions=regions,
        beats=sorted(beats),
        downbeats=sorted(downbeats),
    )
