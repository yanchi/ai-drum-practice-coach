"""Signal utilities. Arrays are float32 shaped (channels, samples)."""

from __future__ import annotations

import numpy as np

_EPS = 1e-12


def resample(audio: np.ndarray, from_sr: int, to_sr: int) -> np.ndarray:
    """Resample with julius (symmetric sinc filter, no time shift; research R-06)."""
    if from_sr == to_sr:
        return audio
    import julius
    import torch

    tensor = torch.from_numpy(np.ascontiguousarray(audio, dtype=np.float32))
    return julius.resample_frac(tensor, from_sr, to_sr).numpy().astype(np.float32)


def fit_length(audio: np.ndarray, num_samples: int) -> np.ndarray:
    length = audio.shape[1]
    if length >= num_samples:
        return audio[:, :num_samples]
    return np.pad(audio, ((0, 0), (0, num_samples - length)))


def match_channels(audio: np.ndarray, channels: int) -> np.ndarray:
    if audio.shape[0] == channels:
        return audio
    if channels == 1:
        return audio.mean(axis=0, keepdims=True)
    if audio.shape[0] == 1:
        return np.repeat(audio, channels, axis=0)
    raise ValueError(f"cannot convert {audio.shape[0]} channels to {channels}")


def peak(audio: np.ndarray) -> float:
    return float(np.max(np.abs(audio))) if audio.size else 0.0


def _rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))


def rms_db_relative(stem: np.ndarray, mix: np.ndarray) -> float:
    return 20 * np.log10(max(_rms(stem), _EPS) / max(_rms(mix), _EPS))


def loudest_window_start(mono: np.ndarray, sr: int, sec: float = 30) -> float:
    """Start time (seconds, on a 1 s grid) of the window with the most energy."""
    window = int(sec * sr)
    if len(mono) <= window:
        return 0.0
    energy = np.concatenate([[0.0], np.cumsum(np.square(mono, dtype=np.float64))])
    starts = np.arange(0, len(mono) - window + 1, sr)
    totals = energy[starts + window] - energy[starts]
    return float(starts[int(np.argmax(totals))] / sr)


def estimate_lag(
    reference: np.ndarray,
    target: np.ndarray,
    sr: int,
    window_sec: float = 30,
    max_lag_sec: float = 0.5,
) -> tuple[int, float]:
    """Delay of `target` relative to `reference` in samples (positive = target is later).

    Uses FFT cross-correlation over the loudest window (research R-07).
    Returns (lag_samples, window_start_sec).
    """
    ref = reference.mean(axis=0)
    tgt = target.mean(axis=0)
    length = min(len(ref), len(tgt))
    start_sec = loudest_window_start(ref[:length], sr, window_sec)
    start = int(start_sec * sr)
    stop = min(length, start + int(window_sec * sr))
    r, t = ref[start:stop].astype(np.float64), tgt[start:stop].astype(np.float64)

    size = 1 << int(np.ceil(np.log2(2 * len(r))))
    corr = np.fft.irfft(np.fft.rfft(t, size) * np.conj(np.fft.rfft(r, size)), size)
    max_lag = min(int(max_lag_sec * sr), len(r) - 1)
    lags = np.concatenate([np.arange(0, max_lag + 1), np.arange(-max_lag, 0)])
    values = np.concatenate([corr[: max_lag + 1], corr[size - max_lag :]])
    return int(lags[int(np.argmax(values))]), start_sec
