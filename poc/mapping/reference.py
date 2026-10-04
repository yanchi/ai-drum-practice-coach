"""Map drum events onto bars, beats and grid positions (specs/003-beat-bar-mapping R-05)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np

from poc.beat.run import load_beatgrid
from poc.domain import BeatGrid, BeatPosition, DrumEvent, ReferencePerformance
from poc.errors import PocError, UserInputError

# Grid positions inside a beat: 16th notes and 8th-note triplets ("1" = next beat).
GRID = [
    Fraction(0),
    Fraction(1, 4),
    Fraction(1, 3),
    Fraction(1, 2),
    Fraction(2, 3),
    Fraction(3, 4),
    Fraction(1),
]
GAP_FACTOR = 1.5  # an interval this many times the median has no beats (a break)


def _unmapped(reason: str) -> BeatPosition:
    return BeatPosition(None, None, None, None, None, reason)


def position_of(
    t: float, beats: list[float], downbeats: list[float], meter: int = 4
) -> BeatPosition:
    """Bar, beat, grid position and deviation of time `t` (R-05)."""
    b = np.asarray(beats)
    if len(b) < 2:
        return _unmapped("no_beats")
    median = float(np.median(np.diff(b)))
    if t < b[0]:
        if b[0] - t > median / 2:
            return _unmapped("before_first_beat")
        i, interval = 0, b[1] - b[0]
    else:
        i = int(np.searchsorted(b, t, side="right")) - 1
        if i >= len(b) - 1:
            interval = b[-1] - b[-2]
            if t - b[-1] >= interval:
                return _unmapped("after_last_beat")
            i = len(b) - 1
        else:
            interval = b[i + 1] - b[i]
            if interval > GAP_FACTOR * median:
                return _unmapped("no_beats")
    position = (t - b[i]) / interval
    grid = min(GRID, key=lambda g: abs(position - float(g)))
    grid_time = b[i] + float(grid) * interval
    beat_index = i + 1 if grid == 1 else i
    if grid == 1:
        grid = Fraction(0)

    d = np.asarray(downbeats)
    beat_time = b[beat_index] if beat_index < len(b) else b[-1] + interval
    bar = int(np.searchsorted(d, beat_time + 1e-3, side="right"))
    if bar == 0:
        first = int(np.searchsorted(b, d[0] - 1e-3)) if len(d) else 0
        beat = (beat_index - first) % meter + 1
    else:
        start = int(np.searchsorted(b, d[bar - 1] - 1e-3))
        beat = beat_index - start + 1
    return BeatPosition(
        bar=bar,
        beat=beat,
        position=round(float(position), 6),
        grid=str(grid) if grid else "0",
        deviation_ms=round((t - grid_time) * 1000, 3),
    )


def build_reference(
    beatgrid: BeatGrid, transcription: dict[str, Any], now: datetime | None = None
) -> ReferencePerformance:
    run_id = beatgrid.input["poc1_run_id"]
    if transcription["input"]["poc1_run_id"] != run_id:
        raise UserInputError(
            f"beat grid is for {run_id} but the transcription is for "
            f"{transcription['input']['poc1_run_id']}"
        )
    beats = beatgrid.beat_times
    events = sorted((DrumEvent(**e) for e in transcription["events"]), key=lambda e: e.time_sec)
    now = now or datetime.now().astimezone()
    return ReferencePerformance(
        reference_id=f"{now:%Y%m%d-%H%M%S}_{beatgrid.beatgrid_id.split('_')[-1]}",
        created_at=now.isoformat(timespec="seconds"),
        beatgrid_id=beatgrid.beatgrid_id,
        transcription_id=transcription["transcription_id"],
        poc1_run_id=run_id,
        events=[
            (e, position_of(e.time_sec, beats, beatgrid.downbeats, beatgrid.meter)) for e in events
        ],
    )


def events_in_bars(
    reference: ReferencePerformance, first: int, last: int | None = None
) -> list[tuple[DrumEvent, BeatPosition]]:
    last = first if last is None else last
    return [(e, p) for e, p in reference.events if p.bar is not None and first <= p.bar <= last]


def load_reference(reference_dir: Path) -> ReferencePerformance:
    path = Path(reference_dir) / "reference.json"
    if not path.exists():
        raise UserInputError(
            f"not a reference directory (reference.json not found): {reference_dir}"
        )
    return ReferencePerformance.from_dict(json.loads(path.read_text()))


def run_map(beatgrid_dir: Path, transcription_dir: Path, output_dir: Path) -> Path:
    beatgrid = load_beatgrid(beatgrid_dir)
    path = Path(transcription_dir) / "transcription.json"
    if not path.exists():
        raise UserInputError(f"transcription.json not found in {transcription_dir}")
    reference = build_reference(beatgrid, json.loads(path.read_text()))
    output_dir = Path(output_dir)
    final_dir = output_dir / reference.reference_id
    partial_dir = output_dir / f"{reference.reference_id}.partial"
    if final_dir.exists() or partial_dir.exists():
        raise PocError(f"reference directory already exists: {final_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    partial_dir.mkdir()
    try:
        (partial_dir / "reference.json").write_text(
            json.dumps(reference.to_dict(), indent=2, ensure_ascii=False) + "\n"
        )
        partial_dir.rename(final_dir)
    except BaseException:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise
    return final_dir
