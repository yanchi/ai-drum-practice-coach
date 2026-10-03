import numpy as np
import pytest

from poc.recording.check import loopback_metrics
from poc.recording.record import ClockFit, build_playback, fit_clock

SR = 44100


def test_build_playback_adds_count_in():
    accompaniment = np.full((2, SR), 0.1, dtype=np.float32)
    playback, count_in = build_playback(accompaniment, SR, beats=4, bpm=120)
    assert count_in == 2 * SR  # 4 beats at 120 BPM = 2 s
    assert playback.shape == (2, count_in + SR)
    assert playback.dtype == np.float32
    assert np.all(playback[:, count_in:] == accompaniment)
    beat = SR // 2
    for i in range(4):  # a click at the start of each beat, silence just before
        assert np.max(np.abs(playback[0, i * beat : i * beat + 200])) > 0.05
        assert np.all(playback[0, (i + 1) * beat - 100 : (i + 1) * beat] == 0)


def test_build_playback_mono_accompaniment_is_duplicated():
    playback, _ = build_playback(np.zeros((1, 10), dtype=np.float32), SR, beats=1, bpm=120)
    assert playback.shape[0] == 2


def test_fit_clock_recovers_linear_mapping():
    rng = np.random.default_rng(0)
    frames = np.arange(0, SR * 10, 512)
    times = 100.0 + frames / SR + rng.normal(0, 0.0003, len(frames))  # callback jitter
    fit = fit_clock(times, frames, SR)
    assert isinstance(fit, ClockFit)
    assert fit.seconds_at(100.0 + 5.0) == pytest.approx(5.0, abs=0.0005)
    assert fit.residual_std_ms < 1.0


def test_fit_clock_needs_two_points():
    with pytest.raises(ValueError):
        fit_clock(np.array([1.0]), np.array([0]), SR)


def test_loopback_detected():
    rng = np.random.default_rng(0)
    played = rng.normal(0, 0.1, (2, SR)).astype(np.float32)
    leaked = 0.5 * played + rng.normal(0, 0.001, played.shape)
    result = loopback_metrics(played, leaked)
    assert not result.passed
    assert result.correlation > 0.9


def test_loopback_clean():
    rng = np.random.default_rng(0)
    played = rng.normal(0, 0.1, (2, SR)).astype(np.float32)
    silence = rng.normal(0, 0.0001, played.shape).astype(np.float32)
    result = loopback_metrics(played, silence)
    assert result.passed
    assert result.level_db < -40


def test_calibration_playback_has_one_click_per_beat():
    from poc.recording.record import CALIBRATION_SCHEDULE, calibration_playback

    playback, count_in = calibration_playback(SR)
    beats = sum(n for n, _ in CALIBRATION_SCHEDULE)
    assert count_in == 4 * SR  # 4 beats at 60 BPM
    assert playback.shape == (2, count_in + beats * SR)
    for i in range(beats):
        start = count_in + i * SR
        assert np.max(np.abs(playback[0, start : start + 200])) > 0.05
        assert np.all(playback[0, start + SR // 2 : start + SR - 10] == 0)
