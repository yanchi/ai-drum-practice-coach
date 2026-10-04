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


def synth_drums(hits, sec: float, sr: int = 44100, channels: int = 1) -> np.ndarray:
    """Render (time_sec, instrument, velocity) hits: kick = 60 Hz decaying sine,
    snare = noise + 200 Hz tone, hihat = high-passed noise. Amplitude ∝ velocity / 127."""
    n = int(sec * sr)
    out = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(1)
    for time_sec, instrument, velocity in hits:
        start = int(round(time_sec * sr))
        length = int((0.25 if instrument == "kick" else 0.12) * sr)
        t = np.arange(length) / sr
        if instrument == "kick":
            sound = np.sin(2 * np.pi * 60 * t) * np.exp(-t * 18)
        elif instrument == "snare":
            tone = np.sin(2 * np.pi * 200 * t)
            sound = (rng.uniform(-1, 1, length) * 0.7 + tone) * np.exp(-t * 30)
        else:
            noise = rng.uniform(-1, 1, length)
            sound = np.diff(noise, prepend=0.0) * 0.5 * np.exp(-t * 60)
        stop = min(n, start + length)
        if start < n:
            out[start:stop] += (velocity / 127) * 0.8 * sound[: stop - start].astype(np.float32)
    return np.tile(out, (channels, 1))


class FakeTranscriber:
    """Returns a fixed list of DrumEvent."""

    def __init__(self, events=None, thresholds=(0.2,)):
        self.events = list(events or [])
        self.thresholds = list(thresholds)

    def transcribe(self, audio_path):
        from poc.domain import TranscriberInfo

        return list(self.events), TranscriberInfo(
            method="fake",
            version="0",
            params={"thresholds": self.thresholds},
            device="cpu",
        )


# --- PoC 3 helpers ---


def synthetic_beats(
    bpm: float, sec: float, start: float = 0.5, jitter_ms: float = 0, seed: int = 0
):
    """Beat times at a steady tempo, optionally with random timing jitter."""
    rng = np.random.default_rng(seed)
    step = 60 / bpm
    times = np.arange(start, sec, step)
    if jitter_ms:
        times = times + rng.normal(0, jitter_ms / 1000, len(times))
    return [round(float(t), 4) for t in times]


def downbeat_activation(
    n_beats: int, phase: int = 0, flips=None, noise: float = 0.0, seed: int = 0
):
    """Per-beat downbeat activation: high where (i + phase) % 4 == 0.
    `flips=[(from_beat, new_phase)]` changes the phase from that beat on."""
    rng = np.random.default_rng(seed)
    changes = dict(flips or [])
    out = []
    for i in range(n_beats):
        phase = changes.get(i, phase)
        value = 0.9 if (i + phase) % 4 == 0 else 0.05
        out.append(float(np.clip(value + rng.normal(0, noise), 0.0, 1.0)))
    return out


class FakeBeatEstimator:
    """Returns given beats / downbeats / activations without running a model."""

    def __init__(self, beats, activation, downbeats=None):
        self.beats = beats
        self.activation = activation
        self.downbeats = (
            downbeats
            if downbeats is not None
            else [t for t, a in zip(beats, activation, strict=True) if a > 0.5]
        )
        self.calls = 0

    def estimate(self, signal, sr):
        from poc.beat.base import BeatEstimate

        self.calls += 1
        return BeatEstimate(
            beats=list(self.beats),
            downbeats=list(self.downbeats),
            downbeat_activation=list(self.activation),
            info={"method": "fake", "version": "0", "checkpoint": "fake", "device": "cpu"},
        )
