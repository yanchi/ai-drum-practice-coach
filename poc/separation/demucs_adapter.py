"""Demucs v4 adapter. Demucs-specific types stay inside this module (Constitution III)."""

from __future__ import annotations

import random
from importlib.metadata import version

import numpy as np

from poc.audio.signal import fit_length, match_channels, resample
from poc.domain import SeparatorInfo
from poc.errors import SeparationError
from poc.separation.base import SeparationOutput

OVERLAP = 0.25


def resolve_device(device: str) -> str:
    import torch

    if device == "auto":
        return "mps" if torch.backends.mps.is_available() else "cpu"
    return device


class DemucsSeparator:
    def __init__(self, model: str = "htdemucs", device: str = "auto", seed: int = 0):
        self.model_name = model
        self.device = resolve_device(device)
        self.seed = seed
        self._separator = None

    def _load(self):
        if self._separator is None:
            from demucs.api import Separator

            # shifts=0 disables Demucs' random time shifts so runs are reproducible (research R-02).
            self._separator = Separator(
                model=self.model_name,
                device=self.device,
                shifts=0,
                overlap=OVERLAP,
                split=True,
                progress=False,
            )
        return self._separator

    def _seed_everything(self) -> None:
        import torch

        random.seed(self.seed)
        np.random.seed(self.seed)
        torch.manual_seed(self.seed)

    def separate(self, audio: np.ndarray, sample_rate: int) -> SeparationOutput:
        import torch

        channels, num_samples = audio.shape
        try:
            separator = self._load()
            self._seed_everything()
            model_sr = separator.samplerate
            mix = match_channels(audio, separator.audio_channels)
            mix = resample(mix, sample_rate, model_sr)
            _, stems = separator.separate_tensor(torch.from_numpy(mix), model_sr)
        except (RuntimeError, MemoryError) as exc:
            hint = " (try --device cpu)" if self.device != "cpu" else ""
            raise SeparationError(f"{exc}{hint}") from exc

        stems = {name: wav.cpu().numpy().astype(np.float32) for name, wav in stems.items()}
        drums = stems.pop("drums")
        accompaniment = np.sum(list(stems.values()), axis=0).astype(np.float32)

        def restore(stem: np.ndarray) -> np.ndarray:
            stem = fit_length(resample(stem, model_sr, sample_rate), num_samples)
            return match_channels(stem, channels).astype(np.float32)

        return SeparationOutput(
            drums=restore(drums),
            accompaniment=restore(accompaniment),
            info=SeparatorInfo(
                method="demucs",
                version=version("demucs"),
                model=self.model_name,
                params={
                    "shifts": 0,
                    "overlap": OVERLAP,
                    "segment": None,
                    "split": True,
                    "seed": self.seed,
                },
                device=self.device,
                model_samplerate=model_sr,
            ),
        )
