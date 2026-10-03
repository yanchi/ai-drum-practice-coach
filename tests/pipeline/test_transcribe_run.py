import json
import re
import shutil

import pytest
import soundfile as sf
from conftest import FakeTranscriber, click_track, write_wav

from poc.domain import DrumEvent
from poc.errors import UserInputError
from poc.transcription.run import run_transcription

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

SR = 44100


@pytest.fixture
def poc1_run(tmp_path):
    """A minimal PoC 1 run directory with an input song, drums.wav and accompaniment.wav."""
    song = write_wav(tmp_path, "song.wav", click_track(120, 3, SR), SR)
    run_dir = tmp_path / "runs" / "20261004-000000_abcdef12"
    run_dir.mkdir(parents=True)
    write_wav(run_dir, "drums.wav", click_track(120, 3, SR), SR, subtype="FLOAT")
    write_wav(run_dir, "accompaniment.wav", click_track(60, 3, SR), SR, subtype="FLOAT")
    run = {
        "schema_version": 1,
        "run_id": run_dir.name,
        "song": {"path": str(song), "sha256": "abcdef12" + "0" * 56},
    }
    (run_dir / "run.json").write_text(json.dumps(run))
    return run_dir


EVENTS = [DrumEvent(1.0, "snare", 0.9), DrumEvent(0.5, "kick", 0.8), DrumEvent(0.5, "hihat", 0.4)]


@pytest.mark.parametrize(
    ("kind", "expected"),
    [("drum_stem", "drums.wav"), ("mix", "song.wav"), ("accompaniment", "accompaniment.wav")],
)
def test_input_selection(tmp_path, poc1_run, kind, expected):
    out = run_transcription(poc1_run, kind, tmp_path / "t", FakeTranscriber(EVENTS))
    data = json.loads((out / "transcription.json").read_text())
    assert data["input"]["kind"] == kind
    assert data["input"]["audio_path"].endswith(expected)
    assert data["input"]["poc1_run_id"] == poc1_run.name


def test_outputs(tmp_path, poc1_run):
    out = run_transcription(poc1_run, "drum_stem", tmp_path / "t", FakeTranscriber(EVENTS))

    assert re.fullmatch(r"\d{8}-\d{6}_[0-9a-f]{8}", out.name)
    assert {p.name for p in out.iterdir()} == {"transcription.json", "events.mid", "check.wav"}
    data = json.loads((out / "transcription.json").read_text())
    assert data["schema_version"] == 1
    assert [e["time_sec"] for e in data["events"]] == [0.5, 0.5, 1.0]
    assert data["event_counts"] == {"kick": 1, "hihat": 1, "snare": 1}
    assert data["transcriber"]["method"] == "fake"
    assert set(data["timings_sec"]) == {"load", "transcribe", "write", "total"}
    assert data["peak_memory"]["rss_bytes"] > 0
    assert data["environment"]["python"]
    assert data["warnings"] == []

    check, sr = sf.read(out / "check.wav", always_2d=True)
    assert sr == SR
    assert check.shape[0] == 3 * SR  # same length as the PoC 1 input song


def test_no_events_warning(tmp_path, poc1_run):
    out = run_transcription(poc1_run, "drum_stem", tmp_path / "t", FakeTranscriber([]))
    data = json.loads((out / "transcription.json").read_text())
    assert [w["code"] for w in data["warnings"]] == ["no_events"]


def test_missing_accompaniment(tmp_path, poc1_run):
    (poc1_run / "accompaniment.wav").unlink()
    with pytest.raises(UserInputError):
        run_transcription(poc1_run, "accompaniment", tmp_path / "t", FakeTranscriber(EVENTS))


def test_not_a_run_directory(tmp_path):
    with pytest.raises(UserInputError):
        run_transcription(tmp_path, "drum_stem", tmp_path / "t", FakeTranscriber(EVENTS))


def test_failure_leaves_nothing(tmp_path, poc1_run):
    class Broken:
        def transcribe(self, audio_path):
            raise RuntimeError("boom")

    out_dir = tmp_path / "t"
    with pytest.raises(RuntimeError):
        run_transcription(poc1_run, "drum_stem", out_dir, Broken())
    assert list(out_dir.iterdir()) == []
