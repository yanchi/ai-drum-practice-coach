"""Evaluation sheet (evaluation.yaml) filled in by the developer (contracts/files.md)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from poc.domain import ISSUE_CHOICES, SeparationEvaluation
from poc.errors import UserInputError

SHEET_SCHEMA_VERSION = 2
VERDICTS = ("ok", "ng")

_TEMPLATE = """\
# 評価シート (PoC 1)。記入したら `uv run poc summarize` で集計する。
# verdict: Drum Stem を聴いて、PoC 2 の打撃検出に使えそうなら ok、使えなさそうなら ng
# issues: 気になった楽器・問題のリスト (例: [hihat, bleed])。なければ []
#   kick / snare / hihat / toms / cymbals = その楽器が消えている・弱い
#   bleed = 他の楽器が混ざる / artifacts = 音質の劣化
schema_version: {schema_version}
run_id: {run_id}
song_label: {song_label}
genre: ""
evaluated_at: ""
verdict: null
issues: []
notes: ""
"""


class SheetValidationError(UserInputError):
    def __init__(self, path: Path, field: str, message: str):
        super().__init__(f"{path}: {field}: {message}")


def render_template(run_id: str, song_label: str = "") -> str:
    # JSON strings are valid YAML double-quoted scalars.
    return _TEMPLATE.format(
        schema_version=SHEET_SCHEMA_VERSION,
        run_id=run_id,
        song_label=json.dumps(song_label, ensure_ascii=False),
    )


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def load_sheet(path: Path) -> SeparationEvaluation | None:
    """Load and validate a sheet. Returns None until `verdict` and `song_label` are filled in.

    Values that are filled in but invalid raise SheetValidationError.
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

    verdict = data.get("verdict")
    if verdict is not None:
        if not isinstance(verdict, str) or verdict.lower() not in VERDICTS:
            fail("verdict", f"must be ok or ng, got {verdict!r}")
        verdict = verdict.lower()

    issues = data.get("issues") or []
    if not isinstance(issues, list):
        fail("issues", "must be a list, e.g. [hihat, bleed]")
    unknown = [i for i in issues if i not in ISSUE_CHOICES]
    if unknown:
        fail("issues", f"unknown {unknown}; choose from {', '.join(ISSUE_CHOICES)}")

    song_label = _text(data.get("song_label"))
    if verdict is None or not song_label:
        return None

    return SeparationEvaluation(
        run_id=_text(data.get("run_id")),
        song_label=song_label,
        genre=_text(data.get("genre")),
        evaluated_at=_text(data.get("evaluated_at")),
        verdict=verdict,
        issues=list(dict.fromkeys(issues)),
        notes=_text(data.get("notes")),
    )
