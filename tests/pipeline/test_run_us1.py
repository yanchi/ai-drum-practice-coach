import json
import re
import shutil

import pytest
import soundfile as sf
from conftest import FakeSeparator, click_track, write_wav

from poc.cli import main
from poc.errors import SeparationError
from poc.evaluation.run import run_separation

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.fixture
def song_path(tmp_path):
    return write_wav(tmp_path, "song.wav", click_track(120, 3, 48000), 48000)


def warning_codes(run_dir):
    data = json.loads((run_dir / "run.json").read_text())
    return {w["code"] for w in data["warnings"]}


def test_successful_run(tmp_path, song_path):
    out = tmp_path / "runs"
    run_dir = run_separation(song_path, out, FakeSeparator(), write_accompaniment=False)

    assert re.fullmatch(r"\d{8}-\d{6}_[0-9a-f]{8}", run_dir.name)
    assert [p.name for p in out.iterdir()] == [run_dir.name]

    drums, sr = sf.read(run_dir / "drums.wav", always_2d=True)
    info = sf.info(run_dir / "drums.wav")
    assert sr == 48000
    assert drums.shape == (3 * 48000, 2)
    assert info.subtype == "FLOAT"

    data = json.loads((run_dir / "run.json").read_text())
    assert data["schema_version"] == 1
    assert data["status"] == "succeeded"
    assert data["song"]["sample_rate"] == 48000
    assert data["alignment"]["passed"] is True
    assert data["alignment"]["lag_samples"] == 0
    assert [s["kind"] for s in data["stems"]] == ["drums"]
    assert data["warnings"] == []
    assert f"run_id: {run_dir.name}" in (run_dir / "evaluation.yaml").read_text()


def test_failure_leaves_nothing(tmp_path, song_path):
    out = tmp_path / "runs"
    separator = FakeSeparator(error=SeparationError("boom"))
    with pytest.raises(SeparationError):
        run_separation(song_path, out, separator, write_accompaniment=False)
    assert list(out.iterdir()) == []


def test_drums_nearly_silent(tmp_path, song_path):
    run_dir = run_separation(
        song_path, tmp_path / "runs", FakeSeparator(drums_gain=0.01), write_accompaniment=False
    )
    assert "drums_nearly_silent" in warning_codes(run_dir)


def test_clipping_is_reported_and_not_clipped(tmp_path):
    path = write_wav(tmp_path, "song.wav", click_track(120, 3, 44100, amp=0.9), 44100)
    run_dir = run_separation(
        path, tmp_path / "runs", FakeSeparator(drums_gain=1.5), write_accompaniment=False
    )
    assert "clipping_risk" in warning_codes(run_dir)
    drums, _ = sf.read(run_dir / "drums.wav")
    assert abs(drums).max() > 1.0


def test_cli_rejects_drm(tmp_path, capsys):
    path = tmp_path / "song.m4p"
    path.write_bytes(b"\x00" * 16)
    code = main(["separate", str(path), "--output-dir", str(tmp_path / "runs")])
    assert code == 2
    assert "DRM-protected" in capsys.readouterr().err
    assert not (tmp_path / "runs").exists() or list((tmp_path / "runs").iterdir()) == []
