"""`poc check-repro`: compare the drum stems of two runs of the same input (SC-006)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from poc.errors import UserInputError


def _load_run(run_dir: Path) -> dict[str, Any]:
    path = Path(run_dir) / "run.json"
    if not path.exists():
        raise UserInputError(f"run.json not found in {run_dir}")
    return json.loads(path.read_text())


def _settings(run: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in run["separator"].items() if k != "device"}


def compare_runs(run_a: Path, run_b: Path, tolerance: float = 1e-4) -> tuple[float, bool]:
    """Return (max absolute sample difference of drums.wav, passed).

    Runs must share the input and separator settings; the device may differ.
    """
    a, b = _load_run(run_a), _load_run(run_b)
    if a["song"]["sha256"] != b["song"]["sha256"]:
        raise UserInputError("the two runs have different inputs (song.sha256)")
    if _settings(a) != _settings(b):
        raise UserInputError("the two runs used different separator settings")

    drums_a, _ = sf.read(Path(run_a) / "drums.wav", dtype="float32", always_2d=True)
    drums_b, _ = sf.read(Path(run_b) / "drums.wav", dtype="float32", always_2d=True)
    if drums_a.shape != drums_b.shape:
        return float("inf"), False
    diff = float(np.max(np.abs(drums_a - drums_b))) if drums_a.size else 0.0
    return diff, diff <= tolerance
