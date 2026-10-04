import json

import pytest

from poc.beat.beats import click_beats
from poc.beat.grid import drum_offset_sec, fill_beat_gaps
from poc.errors import UserInputError


def test_fill_beat_gaps_inserts_skipped_beats():
    beats = [0.0, 0.32, 0.64, 1.28, 1.6, 2.56, 2.88]  # one beat missing, then two
    filled = fill_beat_gaps(beats)
    assert filled == pytest.approx([0.0, 0.32, 0.64, 0.96, 1.28, 1.6, 1.92, 2.24, 2.56, 2.88])


def test_fill_beat_gaps_keeps_long_or_uneven_gaps():
    beats = [0.0, 0.32, 0.64, 0.96, 10.0, 10.32, 10.64, 11.12, 11.44]  # break; 1.5-beat gap
    assert fill_beat_gaps(beats) == beats


def test_drum_offset_sec_is_median_onset_minus_beat():
    beats = [0.0, 0.32, 0.64, 0.96, 1.28]
    onsets = [-0.02, 0.30, 0.62, 0.95, 1.26, 0.48]  # 0.48: off the beat, ignored
    assert drum_offset_sec(beats, onsets) == pytest.approx(-0.02)


def test_drum_offset_sec_without_onsets_near_beats():
    assert drum_offset_sec([0.0, 0.32], [0.16]) is None
    assert drum_offset_sec([0.0, 0.32], []) is None


def test_click_beats_shifts_onto_latest_drum_stem_transcription(tmp_path):
    run_dir = tmp_path / "runs" / "20261004-000000_abcd"
    run_dir.mkdir(parents=True)
    beats = [0.5 + 0.32 * i for i in range(10)]
    del beats[4]  # a skipped beat
    (run_dir / "beats.json").write_text(json.dumps({"beats": beats, "downbeats": [0.5, 1.78]}))
    for created_at, offset in [
        ("2026-10-04T01:00:00+09:00", -0.05),
        ("2026-10-04T02:00:00+09:00", -0.02),
    ]:
        tr = tmp_path / "tr" / created_at[11:13]
        tr.mkdir(parents=True)
        events = [{"time_sec": t + offset, "instrument": "kick", "strength": 1.0} for t in beats]
        (tr / "transcription.json").write_text(
            json.dumps(
                {
                    "transcription_id": created_at[11:13],
                    "created_at": created_at,
                    "input": {"kind": "drum_stem", "poc1_run_id": run_dir.name},
                    "events": events,
                }
            )
        )
    shifted, downbeats, info = click_beats(run_dir, tmp_path / "tr")
    assert info == {
        "beats_file": "beats.json",
        "filled_beats": 1,
        "offset_ms": -20.0,
        "offset_from": "02",
    }
    assert len(shifted) == 10
    assert shifted[0] == pytest.approx(0.48)
    assert downbeats == pytest.approx([0.48, 1.76])


def test_click_beats_needs_a_transcription(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "beats.json").write_text(json.dumps({"beats": [0.0, 0.32, 0.64], "downbeats": []}))
    with pytest.raises(UserInputError):
        click_beats(run_dir, tmp_path / "none")
