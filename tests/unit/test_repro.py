import json

import numpy as np
import pytest
import soundfile as sf
from conftest import sine

from poc.errors import UserInputError
from poc.evaluation.repro import compare_runs


def make_run(tmp_path, name, drums, *, sha="a" * 64, params=None, device="mps"):
    run_dir = tmp_path / name
    run_dir.mkdir()
    run = {
        "schema_version": 1,
        "run_id": name,
        "song": {"sha256": sha},
        "separator": {
            "method": "demucs",
            "version": "4.1.0",
            "model": "htdemucs",
            "params": params or {"shifts": 0, "seed": 0},
            "device": device,
        },
    }
    (run_dir / "run.json").write_text(json.dumps(run))
    sf.write(run_dir / "drums.wav", drums.T, 44100, subtype="FLOAT")
    return run_dir


@pytest.fixture
def drums():
    return sine(220, 1, 44100)


def test_identical_runs_pass(tmp_path, drums):
    a = make_run(tmp_path, "a", drums)
    b = make_run(tmp_path, "b", drums)
    diff, passed = compare_runs(a, b)
    assert diff == 0.0
    assert passed


def test_noise_above_tolerance_fails(tmp_path, drums):
    a = make_run(tmp_path, "a", drums)
    b = make_run(tmp_path, "b", drums + np.float32(1e-3))
    diff, passed = compare_runs(a, b, tolerance=1e-4)
    assert diff == pytest.approx(1e-3, rel=1e-3)
    assert not passed


def test_different_device_is_allowed(tmp_path, drums):
    a = make_run(tmp_path, "a", drums, device="mps")
    b = make_run(tmp_path, "b", drums, device="cpu")
    assert compare_runs(a, b)[1]


def test_different_length_fails(tmp_path, drums):
    a = make_run(tmp_path, "a", drums)
    b = make_run(tmp_path, "b", drums[:, :-1])
    diff, passed = compare_runs(a, b)
    assert diff == float("inf")
    assert not passed


@pytest.mark.parametrize("kwargs", [{"sha": "b" * 64}, {"params": {"shifts": 1, "seed": 0}}])
def test_different_input_or_settings_is_rejected(tmp_path, drums, kwargs):
    a = make_run(tmp_path, "a", drums)
    b = make_run(tmp_path, "b", drums, **kwargs)
    with pytest.raises(UserInputError):
        compare_runs(a, b)


def test_missing_run_is_rejected(tmp_path, drums):
    a = make_run(tmp_path, "a", drums)
    with pytest.raises(UserInputError):
        compare_runs(a, tmp_path / "missing")
