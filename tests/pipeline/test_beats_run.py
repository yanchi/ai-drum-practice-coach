import json

import pytest
from conftest import FakeBeatEstimator, click_track, downbeat_activation, synthetic_beats, write_wav

from poc.beat.run import run_beats
from poc.errors import UserInputError

SR = 44100
BPM = 120


@pytest.fixture
def poc1_run(tmp_path):
    """A fake PoC 1 run: song.wav (clicks), drums.wav, run.json, and a drum stem transcription
    whose kicks sit 15 ms before the estimated beats."""
    run_dir = tmp_path / "runs" / "20261004-000000_abcdef12"
    run_dir.mkdir(parents=True)
    song = write_wav(tmp_path, "song.wav", click_track(BPM, 20, SR), SR)
    write_wav(run_dir, "drums.wav", click_track(BPM, 20, SR), SR)
    (run_dir / "run.json").write_text(
        json.dumps({"run_id": run_dir.name, "song": {"path": str(song)}})
    )
    beats = synthetic_beats(BPM, 19.5)
    tr_dir = tmp_path / "transcriptions" / "20261004-000001_drum_stem_aaaa"
    tr_dir.mkdir(parents=True)
    (tr_dir / "transcription.json").write_text(
        json.dumps(
            {
                "transcription_id": tr_dir.name,
                "created_at": "2026-10-04T00:00:01+09:00",
                "input": {"kind": "drum_stem", "poc1_run_id": run_dir.name},
                "events": [
                    {"time_sec": round(t - 0.015, 4), "instrument": "kick", "strength": 0.9}
                    for t in beats
                ],
            }
        )
    )
    return run_dir, tmp_path / "transcriptions", beats


def estimator_for(beats, skip=(9,)):
    activation = downbeat_activation(len(beats))
    kept = [i for i in range(len(beats)) if i not in skip]
    return FakeBeatEstimator([beats[i] for i in kept], [activation[i] for i in kept])


def test_run_beats_writes_grid_and_check_wav(poc1_run, tmp_path):
    run_dir, transcriptions, beats = poc1_run
    out = run_beats(
        run_dir,
        "mix",
        tmp_path / "out",
        estimator_for(beats),
        offset=True,
        transcriptions_dir=transcriptions,
    )
    grid = json.loads((out / "beatgrid.json").read_text())
    assert (out / "check.wav").exists()
    assert grid["input"]["kind"] == "mix"
    assert grid["input"]["poc1_run_id"] == run_dir.name
    assert grid["offset"]["applied_ms"] == pytest.approx(-15, abs=0.5)
    assert grid["offset"]["from_transcription_id"] == "20261004-000001_drum_stem_aaaa"
    assert grid["downbeat_source"] == "regularized"
    assert grid["meter"] == 4
    assert grid["bpm"] == pytest.approx(BPM, abs=0.5)
    assert [b["inferred"] for b in grid["beats"]].count(True) == 1
    assert grid["beats"][9]["inferred"] and grid["beats"][9]["downbeat_activation"] is None
    assert grid["beats"][0]["time_sec"] == pytest.approx(beats[0] - 0.015, abs=1e-3)
    assert grid["downbeats"][:3] == pytest.approx([t - 0.015 for t in beats[0:9:4]], abs=1e-3)
    assert grid["timings_sec"]["total"] >= 0
    assert grid["environment"]


def test_run_beats_options(poc1_run, tmp_path):
    run_dir, transcriptions, beats = poc1_run
    no_offset = run_beats(  # no offset by default; needs no transcription
        run_dir, "drum_stem", tmp_path / "a", estimator_for(beats), regularize=False
    )
    grid = json.loads((no_offset / "beatgrid.json").read_text())
    assert grid["offset"] == {"applied_ms": 0.0, "from_transcription_id": None}
    assert grid["downbeat_source"] == "raw"
    assert grid["input"]["kind"] == "drum_stem"
    with pytest.raises(UserInputError):
        run_beats(
            run_dir,
            "mix",
            tmp_path / "b",
            estimator_for(beats),
            offset=True,
            transcriptions_dir=tmp_path / "x",
        )
