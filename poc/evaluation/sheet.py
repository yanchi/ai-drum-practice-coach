"""Evaluation sheet (evaluation.yaml) filled in by the developer (contracts/files.md)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from poc.domain import (
    INSTRUMENTS,
    CheckSection,
    HitCount,
    ListeningRating,
    SeparationEvaluation,
)
from poc.errors import UserInputError

SHEET_SCHEMA_VERSION = 1
SECTION_LABELS = ("verse", "chorus", "fill")
RATING_FIELDS = ("drum_clarity", "bleed", "artifacts")
TEXT_FIELDS = ("song_label", "genre", "evaluated_at")

_SECTION_TEMPLATE = """\
  - label: {label}
    start_sec: null
    end_sec: null
    counts:
      kick:  {{original: null, detected: null}}
      snare: {{original: null, detected: null}}
      hihat: {{original: null, detected: null}}
    ghost_notes_memo: ""
"""

_TEMPLATE = """\
# 評価シート (PoC 1)。記入したら `uv run poc summarize` で集計する。
# 評価の仕方:
#   listening: 1-5 の整数。drum_clarity 5=ドラムがはっきり聴こえる / bleed 5=他楽器の混入なし / artifacts 5=劣化なし
#   sections: Verse・Chorus・Fill 前後から 4 小節ずつ。原曲で聴こえる打撃 (ゴーストノートを除く) を original に、
#             Drum Stem で確認できた打撃を detected に書く。
schema_version: {schema_version}
run_id: {run_id}
song_label: ""
genre: ""
evaluated_at: ""
listening:
  drum_clarity: null
  bleed: null
  artifacts: null
sections:
{sections}notes: ""
"""


class SheetValidationError(UserInputError):
    def __init__(self, path: Path, field: str, message: str):
        super().__init__(f"{path}: {field}: {message}")


def render_template(run_id: str) -> str:
    sections = "".join(_SECTION_TEMPLATE.format(label=label) for label in SECTION_LABELS)
    return _TEMPLATE.format(schema_version=SHEET_SCHEMA_VERSION, run_id=run_id, sections=sections)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def load_sheet(path: Path) -> SeparationEvaluation | None:
    """Load and validate a sheet. Returns None while the sheet is not fully filled in.

    A sheet is incomplete when any value is null or a text field is empty. Values that
    are filled in but invalid raise SheetValidationError.
    """
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise SheetValidationError(path, "(file)", f"invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SheetValidationError(path, "(file)", "expected a mapping")

    def fail(field: str, message: str):
        raise SheetValidationError(path, field, message)

    if data.get("schema_version") != SHEET_SCHEMA_VERSION:
        fail("schema_version", f"unsupported version {data.get('schema_version')!r}")

    sections = data.get("sections")
    if not isinstance(sections, list) or len(sections) != len(SECTION_LABELS):
        fail("sections", "exactly 3 sections (verse, chorus, fill) are required")
    labels = [s.get("label") if isinstance(s, dict) else None for s in sections]
    if sorted(map(str, labels)) != sorted(SECTION_LABELS):
        fail("sections", "labels must be verse, chorus and fill, once each")

    incomplete = any(data.get(name) in (None, "") for name in TEXT_FIELDS)

    listening = data.get("listening") or {}
    for name in RATING_FIELDS:
        value = listening.get(name)
        if value is None:
            incomplete = True
        elif not _is_int(value) or not 1 <= value <= 5:
            fail(f"listening.{name}", f"must be an integer from 1 to 5, got {value!r}")

    for i, section in enumerate(sections):
        start, end = section.get("start_sec"), section.get("end_sec")
        if start is None or end is None:
            incomplete = True
        else:
            if not _is_number(start) or start < 0:
                fail(f"sections[{i}].start_sec", f"must be a number >= 0, got {start!r}")
            if not _is_number(end) or end <= start:
                fail(f"sections[{i}].end_sec", f"must be greater than start_sec, got {end!r}")
        counts = section.get("counts") or {}
        for inst in INSTRUMENTS:
            count = counts.get(inst) or {}
            original, detected = count.get("original"), count.get("detected")
            if original is None or detected is None:
                incomplete = True
                continue
            field = f"sections[{i}].counts.{inst}"
            if not (_is_int(original) and _is_int(detected)) or original < 0 or detected < 0:
                fail(field, "original and detected must be integers >= 0")
            if detected > original:
                fail(field, f"detected ({detected}) must not exceed original ({original})")

    if incomplete:
        return None

    return SeparationEvaluation(
        run_id=str(data.get("run_id")),
        song_label=str(data["song_label"]),
        genre=str(data["genre"]),
        evaluated_at=str(data["evaluated_at"]),
        listening=ListeningRating(**{name: listening[name] for name in RATING_FIELDS}),
        sections=[
            CheckSection(
                label=s["label"],
                start_sec=float(s["start_sec"]),
                end_sec=float(s["end_sec"]),
                counts={inst: HitCount(**s["counts"][inst]) for inst in INSTRUMENTS},
                ghost_notes_memo=str(s.get("ghost_notes_memo") or ""),
            )
            for s in sections
        ],
        notes=str(data.get("notes") or ""),
    )
