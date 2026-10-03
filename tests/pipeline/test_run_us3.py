import json
import shutil

import pytest
from conftest import FakeSeparator, click_track, write_wav

from poc.cli import main
from poc.evaluation.run import run_separation

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def test_run_json_has_costs_and_environment(tmp_path):
    song = write_wav(tmp_path, "song.wav", click_track(120, 3, 44100), 44100)
    run_dir = run_separation(song, tmp_path / "runs", FakeSeparator(), write_accompaniment=False)
    data = json.loads((run_dir / "run.json").read_text())

    assert set(data["timings_sec"]) == {"decode", "separate", "write", "total"}
    assert data["timings_sec"]["total"] >= data["timings_sec"]["separate"]
    assert data["peak_memory"]["rss_bytes"] > 0
    assert data["peak_memory"]["mps_driver_bytes"] is None  # FakeSeparator reports cpu
    assert set(data["environment"]) == {
        "python",
        "torch",
        "demucs",
        "ffmpeg",
        "platform",
        "machine",
    }
    assert data["separator"]["params"]["seed"] == 0


def test_check_repro_cli(tmp_path, capsys):
    song = write_wav(tmp_path, "song.wav", click_track(120, 3, 44100), 44100)
    a = run_separation(song, tmp_path / "a", FakeSeparator(), write_accompaniment=False)
    b = run_separation(song, tmp_path / "b", FakeSeparator(), write_accompaniment=False)

    assert main(["check-repro", str(a), str(b)]) == 0
    assert capsys.readouterr().out.strip() == "max_abs_diff=0 tolerance=0.0001 result=PASS"
