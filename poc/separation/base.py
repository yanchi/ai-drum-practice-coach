"""Boundary between the pipeline and a source separation model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from poc.domain import SeparatorInfo


@dataclass(frozen=True)
class SeparationOutput:
    """Separated stems at the input's sample rate, channel count and length.

    Arrays are float32 shaped (channels, samples).
    """

    drums: np.ndarray
    accompaniment: np.ndarray
    info: SeparatorInfo


class Separator(Protocol):
    def separate(self, audio: np.ndarray, sample_rate: int) -> SeparationOutput: ...
