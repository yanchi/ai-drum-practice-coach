import pytest
from conftest import click_track, sine

from poc.audio.signal import estimate_lag
from poc.separation.demucs_adapter import DemucsSeparator

pytestmark = pytest.mark.slow


def test_demucs_keeps_shape_and_timing():
    sr = 48000
    mix = click_track(120, 10, sr) + sine(220, 10, sr, amp=0.2)

    out = DemucsSeparator(device="cpu").separate(mix, sr)

    assert out.drums.shape == mix.shape
    assert out.accompaniment.shape == mix.shape
    assert out.info.params["shifts"] == 0
    lag, _ = estimate_lag(mix, out.drums + out.accompaniment, sr)
    assert abs(lag) / sr * 1000 <= 1.0
