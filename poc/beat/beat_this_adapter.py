"""Beat This! adapter (docs/poc-plan.md §3.3, specs/003-beat-bar-mapping/research.md R-01).

Beat This! types and frame logits stay inside this module."""

from __future__ import annotations

from importlib.metadata import version

import numpy as np

from poc.beat.base import BeatEstimate

CHECKPOINT = "final0"
FPS = 50  # Beat This! frame rate


class BeatThisEstimator:
    def __init__(self, checkpoint: str = CHECKPOINT, device: str = "cpu"):
        self.checkpoint = checkpoint
        self.device = device
        self._frames = None

    def estimate(self, signal: np.ndarray, sr: int) -> BeatEstimate:
        import torch
        from beat_this.inference import Audio2Frames
        from beat_this.model.postprocessor import Postprocessor

        if self._frames is None:
            self._frames = Audio2Frames(checkpoint_path=self.checkpoint, device=self.device)
        beat_logits, downbeat_logits = self._frames(signal, sr)
        beats, downbeats = Postprocessor(type="minimal", fps=FPS)(beat_logits, downbeat_logits)
        activation = torch.sigmoid(downbeat_logits).cpu().numpy()
        at_beats = []
        for t in beats:  # strongest downbeat activation within one frame of the beat
            frame = int(round(float(t) * FPS))
            window = activation[max(0, frame - 1) : frame + 2]
            at_beats.append(round(float(window.max()), 4) if len(window) else 0.0)
        return BeatEstimate(
            beats=[round(float(t), 4) for t in beats],
            downbeats=[round(float(t), 4) for t in downbeats],
            downbeat_activation=at_beats,
            info={
                "method": "beat_this",
                "version": version("beat-this"),
                "checkpoint": self.checkpoint,
                "device": self.device,
            },
        )


def detect_beats(signal: np.ndarray, sr: int) -> tuple[list[float], list[float]]:
    """Beat and downbeat times in seconds (Beat This! with minimal post-processing)."""
    estimate = BeatThisEstimator().estimate(signal, sr)
    return estimate.beats, estimate.downbeats
