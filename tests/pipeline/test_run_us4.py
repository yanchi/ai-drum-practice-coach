import json
import shutil

import pytest
import soundfile as sf
from conftest import FakeSeparator, click_track, write_wav

from poc.cli import build_parser
from poc.evaluation.run import run_separation

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.fixture
def song_path(tmp_path):
    return write_wav(tmp_path, "song.wav", click_track(120, 3, 48000, channels=1), 48000)


def test_accompaniment_is_written_by_default(tmp_path, song_path):
    run_dir = run_separation(song_path, tmp_path / "runs", FakeSeparator(drums_gain=0.6))

    audio, sr = sf.read(run_dir / "accompaniment.wav", always_2d=True)
    assert sr == 48000
    assert audio.shape == (3 * 48000, 1)
    assert sf.info(run_dir / "accompaniment.wav").subtype == "FLOAT"

    stems = json.loads((run_dir / "run.json").read_text())["stems"]
    assert [s["kind"] for s in stems] == ["drums", "accompaniment"]
    assert stems[1]["path"] == "accompaniment.wav"
    assert stems[1]["num_samples"] == 3 * 48000


def test_no_accompaniment(tmp_path, song_path):
    run_dir = run_separation(
        song_path, tmp_path / "runs", FakeSeparator(), write_accompaniment=False
    )
    assert not (run_dir / "accompaniment.wav").exists()
    stems = json.loads((run_dir / "run.json").read_text())["stems"]
    assert [s["kind"] for s in stems] == ["drums"]


def test_cli_flag():
    parser = build_parser()
    assert parser.parse_args(["separate", "x.wav"]).no_accompaniment is False
    assert parser.parse_args(["separate", "x.wav", "--no-accompaniment"]).no_accompaniment is True
