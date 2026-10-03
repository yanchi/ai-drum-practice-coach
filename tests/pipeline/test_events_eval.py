import json
import shutil

import numpy as np
import pytest
from conftest import FakeSeparator, FakeTranscriber, synth_drums, write_wav

from poc.domain import DrumEvent
from poc.errors import UserInputError
from poc.evaluation.events_eval import evaluate_annotation, evaluate_recording
from poc.recording.calibration import Calibration

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

SR = 44100
RUN_ID = "20261004-000000_abcdef12"
CALIBRATION = Calibration(
    offsets_ms={"kick": 7.0, "snare": 7.0, "hihat": -4.0},
    note_offsets_ms={36: 7.0, 38: 7.0, 42: -4.0},
    std_ms={"kick": 0.4, "snare": 0.7, "hihat": 0.7},
    counts={"kick": 8, "snare": 12, "hihat": 16},
    outliers=0,
)
PLAYED = [(2.0, 36), (2.0, 42), (2.5, 38), (3.0, 42), (3.5, 36)]  # (mix time, note)
INSTRUMENT = {36: "kick", 38: "snare", 42: "hihat"}


@pytest.fixture
def setup(tmp_path):
    rng = np.random.default_rng(0)
    runs = tmp_path / "runs"
    run_dir = runs / RUN_ID
    run_dir.mkdir(parents=True)
    song = write_wav(tmp_path, "song.wav", rng.normal(0, 0.1, (2, 6 * SR)), SR, "FLOAT")
    write_wav(run_dir, "accompaniment.wav", rng.normal(0, 0.1, (2, 6 * SR)), SR, "FLOAT")
    write_wav(run_dir, "drums.wav", np.zeros((2, 6 * SR)), SR, "FLOAT")
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": RUN_ID,
                "song": {"path": str(song)},
                "stems": [{"kind": "drums", "rms_db_relative_to_mix": -6.0}],
            }
        )
    )
    cal_dir = tmp_path / "calibrations" / "20261004-000000_calibration"
    cal_dir.mkdir(parents=True)
    (cal_dir / "calibration.json").write_text(json.dumps(CALIBRATION.to_dict()))

    rec = tmp_path / "recordings" / "20261004-010000_abcdef12"
    rec.mkdir(parents=True)
    shift = 1.0  # count-in only, no latency
    notes = [
        {"time_sec": t + shift - CALIBRATION.note_offsets_ms[n] / 1000, "note": n, "velocity": 90}
        for t, n in PLAYED
    ]
    hits = [(t + shift, INSTRUMENT[n], 90) for t, n in PLAYED]
    write_wav(rec, "drums.wav", synth_drums(hits, 7, SR, channels=2), SR, "FLOAT")
    (rec / "midi_notes.json").write_text(json.dumps(notes))
    (rec / "recording.json").write_text(
        json.dumps(
            {
                "kind": "play_along",
                "recording_id": rec.name,
                "poc1_run_id": RUN_ID,
                "count_in_samples": SR,
                "input_latency_sec": 0.0,
                "output_latency_sec": 0.0,
            }
        )
    )
    return tmp_path, rec


def run(setup, events, **kwargs):
    root, rec = setup
    return evaluate_recording(
        rec,
        separator=FakeSeparator(),
        transcriber=FakeTranscriber(events),
        runs_dir=root / "runs",
        eval_runs_dir=root / "eval_runs",
        transcriptions_dir=root / "tx",
        evaluations_dir=root / "evals",
        calibrations_dir=root / "calibrations",
        **kwargs,
    )


def test_evaluate_recording(setup):
    events = [DrumEvent(t + 0.004, INSTRUMENT[n], 0.8) for t, n in PLAYED]
    events.append(DrumEvent(4.5, "kick", 0.3))  # outside the region [1.5, 4.0]
    out = run(setup, events)
    data = json.loads((out / "evaluation.json").read_text())

    assert set(data["results"]) == {"drum_stem", "mix"}
    kick = data["results"]["drum_stem"]["metrics"]["kick"]
    assert (kick["tp"], kick["fp"], kick["fn"]) == (2, 0, 0)
    assert kick["timing_ms"]["median_signed"] == pytest.approx(4.0, abs=0.01)
    assert data["groundtruth"]["source"] == "td17_midi"
    assert data["groundtruth"]["regions"] == [[1.5, 4.0]]
    assert data["groundtruth"]["alignment"]["calibration_id"] == "20261004-000000_calibration"
    # the fake transcriber returns the same events for the original accompaniment
    assert data["residual_drum_hits"]["counts"] == {"kick": 2, "snare": 1, "hihat": 2}
    root, rec = setup
    assert (rec / "mix.wav").exists() and (rec / "groundtruth.json").exists()
    assert len(list((root / "eval_runs").iterdir())) == 1


def test_missing_calibration(setup):
    root, _ = setup
    shutil.rmtree(root / "calibrations")
    with pytest.raises(UserInputError, match="calibrate"):
        run(setup, [])


def test_evaluate_annotation(setup):
    root, _ = setup
    ann = root / "ann"
    ann.mkdir()
    (ann / "hits.csv").write_text("2.0,k\n2.5,s\n2.75,sg\n")
    (ann / "annotation.yaml").write_text(
        f"schema_version: 1\npoc1_run_id: {RUN_ID}\nregions: [[1.0, 3.0]]\nhits_csv: hits.csv\n"
    )
    events = [DrumEvent(2.01, "kick", 0.5), DrumEvent(2.5, "snare", 0.5)]
    out = evaluate_annotation(
        ann / "annotation.yaml",
        transcriber=FakeTranscriber(events),
        runs_dir=root / "runs",
        transcriptions_dir=root / "tx",
        evaluations_dir=root / "evals",
    )
    data = json.loads((out / "evaluation.json").read_text())
    assert data["groundtruth"]["source"] == "manual"
    assert data["residual_drum_hits"] is None
    snare = data["results"]["drum_stem"]["metrics"]["snare"]
    assert (snare["tp"], snare["fn"]) == (1, 0)
    assert data["results"]["drum_stem"]["ghost_notes"]["snare"] == {"detected": 0, "total": 1}
