import json

import numpy as np
import pytest
from conftest import synthetic_beats

from poc.domain import Beat, BeatGrid, DrumEvent
from poc.errors import UserInputError
from poc.mapping.reference import build_reference, events_in_bars, position_of, run_map

BEATS = synthetic_beats(120, 20, start=1.0)  # 0.5 s per beat
DOWNBEATS = BEATS[::4]


def test_event_just_before_a_downbeat_belongs_to_the_next_bar():
    p = position_of(DOWNBEATS[2] - 0.02, BEATS, DOWNBEATS)
    assert (p.bar, p.beat, p.grid) == (3, 1, "0")
    assert p.deviation_ms == pytest.approx(-20)


@pytest.mark.parametrize(
    ("fraction", "grid"),
    [(0.25, "1/4"), (0.5, "1/2"), (0.75, "3/4"), (1 / 3, "1/3"), (2 / 3, "2/3"), (0.0, "0")],
)
def test_grid_positions(fraction, grid):
    t = BEATS[5] + 0.5 * fraction + 0.004
    p = position_of(t, BEATS, DOWNBEATS)
    assert (p.bar, p.beat, p.grid) == (2, 2, grid)
    assert p.position == pytest.approx(fraction + 0.008, abs=1e-6)
    assert p.deviation_ms == pytest.approx(4, abs=1e-6)


def test_before_first_downbeat_is_bar_zero():
    beats = [0.0, 0.5] + BEATS  # two beats before the first downbeat (1.0 s)
    p = position_of(0.0, beats, DOWNBEATS)
    assert (p.bar, p.beat, p.grid) == (0, 3, "0")


def test_events_outside_the_beats_or_in_gaps_are_unmapped():
    beats = BEATS[:10] + [t + 3.0 for t in BEATS[10:]]  # a 3.5 s gap without beats
    assert position_of(BEATS[9] + 1.5, beats, DOWNBEATS).unmapped_reason == "no_beats"
    assert position_of(0.0, BEATS, DOWNBEATS).unmapped_reason == "before_first_beat"
    late = position_of(BEATS[-1] + 2.0, BEATS, DOWNBEATS)
    assert late.bar is None and late.unmapped_reason == "after_last_beat"


def test_tempo_drift_keeps_grid_positions():
    intervals = np.linspace(0.5, 0.42, 40)
    beats = list(np.round(np.concatenate([[1.0], 1.0 + np.cumsum(intervals)]), 4))
    downbeats = beats[::4]
    for i in (3, 20, 37):
        t = beats[i] + 0.5 * (beats[i + 1] - beats[i])
        assert position_of(t, beats, downbeats).grid == "1/2"


def _grid(run_id="run-a"):
    return BeatGrid(
        beatgrid_id="20261004-000000_mix_abcd1234",
        created_at="2026-10-04T00:00:00+09:00",
        input={"kind": "mix", "poc1_run_id": run_id, "audio_sha256": "x", "duration_sec": 21},
        estimator={"method": "fake"},
        beats=[Beat(t) for t in BEATS],
        downbeats=DOWNBEATS,
        downbeats_raw=DOWNBEATS,
        downbeat_source="regularized",
        meter=4,
        bpm=120.0,
    )


def _transcription(run_id="run-a"):
    events = [
        DrumEvent(BEATS[0], "kick", 0.9),
        DrumEvent(BEATS[0], "cymbal", 0.5),
        DrumEvent(BEATS[4] + 0.25, "hihat", 0.4),
        DrumEvent(BEATS[9], "snare", 0.8),
        DrumEvent(BEATS[13], "tom", 0.6),
    ]
    return {
        "transcription_id": "20261004-000001_drum_stem_aaaa",
        "input": {"kind": "drum_stem", "poc1_run_id": run_id},
        "events": [e.to_dict() for e in events],
    }


def test_build_reference_keeps_all_instruments_and_selects_bars():
    ref = build_reference(_grid(), _transcription())
    assert [e.instrument for e, _ in ref.events] == ["kick", "cymbal", "hihat", "snare", "tom"]
    assert ref.bars == 4
    in_bar_2 = events_in_bars(ref, 2, 3)
    assert [(e.instrument, p.bar, p.beat, p.grid) for e, p in in_bar_2] == [
        ("hihat", 2, 1, "1/2"),
        ("snare", 3, 2, "0"),
    ]


def test_build_reference_rejects_other_runs():
    with pytest.raises(UserInputError):
        build_reference(_grid("run-a"), _transcription("run-b"))


def test_run_map_writes_reference(tmp_path):
    grid_dir = tmp_path / "grid"
    grid_dir.mkdir()
    (grid_dir / "beatgrid.json").write_text(json.dumps(_grid().to_dict()))
    tr_dir = tmp_path / "tr"
    tr_dir.mkdir()
    (tr_dir / "transcription.json").write_text(json.dumps(_transcription()))
    out = run_map(grid_dir, tr_dir, tmp_path / "refs")
    data = json.loads((out / "reference.json").read_text())
    assert data["beatgrid_id"] == "20261004-000000_mix_abcd1234"
    assert data["transcription_id"] == "20261004-000001_drum_stem_aaaa"
    assert data["bars"] == 4 and data["unmapped_count"] == 0
    assert data["events"][2]["position"]["grid"] == "1/2"
