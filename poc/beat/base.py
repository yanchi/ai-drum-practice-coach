"""Beat estimator interface (Constitution III: the beat model can be replaced)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np


@dataclass(frozen=True)
class BeatEstimate:
    beats: list[float]
    downbeats: list[float]
    downbeat_activation: list[float]  # 0-1, sampled at each beat
    info: dict[str, Any] = field(default_factory=dict)  # method / version / checkpoint / device


class BeatEstimator(Protocol):
    def estimate(self, signal: np.ndarray, sr: int) -> BeatEstimate:
        """`signal` is mono, shape (samples,)."""
        ...
