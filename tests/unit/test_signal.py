import numpy as np
import pytest
from conftest import click_track, sine

from poc.audio.signal import (
    estimate_lag,
    fit_length,
    loudest_window_start,
    match_channels,
    peak,
    resample,
    rms_db_relative,
)


def test_resample_round_trip_keeps_timing():
    sr = 48000
    audio = click_track(120, 5, sr)
    back = fit_length(resample(resample(audio, sr, 44100), 44100, sr), audio.shape[1])
    assert back.shape == audio.shape
    lag, _ = estimate_lag(audio, back, sr)
    assert lag == 0


def test_resample_same_rate_is_noop():
    audio = sine(440, 1, 44100)
    assert resample(audio, 44100, 44100) is audio


def test_fit_length_pads_and_truncates():
    audio = np.ones((2, 10), dtype=np.float32)
    assert fit_length(audio, 12).shape == (2, 12)
    assert np.all(fit_length(audio, 12)[:, 10:] == 0)
    assert fit_length(audio, 8).shape == (2, 8)


def test_match_channels():
    stereo = np.stack([np.ones(4), np.zeros(4)]).astype(np.float32)
    mono = match_channels(stereo, 1)
    assert mono.shape == (1, 4)
    assert np.allclose(mono, 0.5)
    assert match_channels(mono, 2).shape == (2, 4)
    assert match_channels(stereo, 2) is stereo


def test_peak_and_rms():
    audio = sine(440, 1, 44100, amp=0.5)
    assert peak(audio) == pytest.approx(0.5, abs=1e-3)
    assert rms_db_relative(audio * 0.1, audio) == pytest.approx(-20.0, abs=0.01)
    assert rms_db_relative(np.zeros_like(audio), audio) < -100


@pytest.mark.parametrize("shift", [10, -10, 0])
def test_estimate_lag(shift):
    sr = 8000
    reference = click_track(100, 40, sr, channels=1)
    target = np.roll(reference, shift, axis=1)
    lag, _ = estimate_lag(reference, target, sr)
    assert lag == shift


def test_loudest_window_is_in_loud_half():
    sr = 1000
    quiet = sine(5, 30, sr, channels=1, amp=0.01)[0]
    loud = sine(5, 30, sr, channels=1, amp=0.9)[0]
    start = loudest_window_start(np.concatenate([quiet, loud]), sr, sec=30)
    assert start >= 25.0


def test_loudest_window_short_signal_starts_at_zero():
    assert loudest_window_start(np.ones(100, dtype=np.float32), 1000, sec=30) == 0.0
