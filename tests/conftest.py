"""Shared test helpers. Tests use synthetic audio only (no copyrighted material)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from poc.domain import SeparatorInfo
from poc.separation.base import SeparationOutput


def sine(freq: float, sec: float, sr: int, channels: int = 2, amp: float = 0.5) -> np.ndarray:
    t = np.arange(int(sec * sr)) / sr
    mono = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.tile(mono, (channels, 1))


def click_track(bpm: float, sec: float, sr: int, channels: int = 2, amp: float = 0.8) -> np.ndarray:
    """Short decaying noise bursts on every beat."""
    n = int(sec * sr)
    mono = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(0)
    burst_len = int(0.01 * sr)
    burst = (rng.uniform(-1, 1, burst_len) * np.exp(-np.linspace(0, 6, burst_len))).astype(
        np.float32
    )
    step = int(60 / bpm * sr)
    for start in range(0, n - burst_len, step):
        mono[start : start + burst_len] += amp * burst
    return np.tile(mono, (channels, 1))


def write_wav(
    directory: Path, name: str, audio: np.ndarray, sr: int, subtype: str = "PCM_16"
) -> Path:
    path = directory / name
    sf.write(path, audio.T, sr, subtype=subtype)
    return path


class FakeSeparator:
    """Returns the input mix as drums and silence as accompaniment."""

    def __init__(self, drums_gain: float = 1.0, error: Exception | None = None):
        self.drums_gain = drums_gain
        self.error = error

    def separate(self, audio: np.ndarray, sample_rate: int) -> SeparationOutput:
        if self.error is not None:
            raise self.error
        drums = (audio * self.drums_gain).astype(np.float32)
        return SeparationOutput(
            drums=drums,
            accompaniment=(audio - drums).astype(np.float32),
            info=SeparatorInfo(
                method="fake",
                version="0",
                model="fake",
                params={"shifts": 0, "seed": 0},
                device="cpu",
                model_samplerate=44100,
            ),
        )


@pytest.fixture
def fake_separator() -> FakeSeparator:
    return FakeSeparator()
