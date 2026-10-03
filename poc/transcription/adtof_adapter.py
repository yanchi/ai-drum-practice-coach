"""ADTOF-pytorch adapter. ADTOF class numbers and activations stay inside this module
(Constitution III). See specs/002-drum-event-extraction/research.md R-01 to R-03."""

from __future__ import annotations

import contextlib
import io
from importlib.metadata import version
from pathlib import Path

import numpy as np

from poc.domain import DrumEvent, Instrument, TranscriberInfo
from poc.errors import UserInputError

ADTOF_COMMIT = "85c192e78f716ea0b111cc8a5ee4a8f6a3a4f8a9"
FPS = 100
# Same peak picking parameters as adtof_pytorch.PeakPicker.
PEAK_PICKING = {
    "pre_avg": 0.1,
    "post_avg": 0.01,
    "pre_max": 0.02,
    "post_max": 0.01,
    "combine": 0.02,
}
# ADTOF output classes (adtof_pytorch.LABELS_5) in model output order.
LABEL_TO_INSTRUMENT: dict[int, Instrument] = {
    35: "kick",
    38: "snare",
    47: "tom",
    42: "hihat",
    49: "cymbal",
}


def parse_thresholds(text: str) -> dict[str, float]:
    """Parse "kick=0.12,hihat=0.12" into per-instrument detection thresholds (research R-16)."""
    thresholds: dict[str, float] = {}
    for item in filter(None, (part.strip() for part in text.split(","))):
        name, sep, value = item.partition("=")
        name = name.strip()
        if not sep or name not in LABEL_TO_INSTRUMENT.values():
            raise UserInputError(
                f"invalid threshold {item!r}; use e.g. kick=0.12 with "
                f"{' / '.join(LABEL_TO_INSTRUMENT.values())}"
            )
        if name in thresholds:
            raise UserInputError(f"threshold for {name} is given twice")
        try:
            number = float(value)
        except ValueError:
            raise UserInputError(f"threshold for {name} is not a number: {value!r}") from None
        if not 0.0 < number < 1.0:
            raise UserInputError(f"threshold for {name} must be between 0 and 1, got {number}")
        thresholds[name] = number
    return thresholds


class AdtofTranscriber:
    def __init__(self, thresholds: dict[str, float] | None = None):
        """`thresholds` overrides the ADTOF defaults for the given instruments only."""
        from adtof_pytorch import FRAME_RNN_THRESHOLDS

        defaults = dict(zip(LABEL_TO_INSTRUMENT.values(), FRAME_RNN_THRESHOLDS, strict=True))
        self.thresholds = {name: float(v) for name, v in {**defaults, **(thresholds or {})}.items()}
        self._model = None

    def _load_model(self):
        if self._model is None:
            from adtof_pytorch import (
                calculate_n_bins,
                create_frame_rnn_model,
                get_default_weights_path,
                load_pytorch_weights,
            )

            model = create_frame_rnn_model(calculate_n_bins())
            # load_pytorch_weights prints progress; keep the CLI's stdout clean.
            with contextlib.redirect_stdout(io.StringIO()):
                model = load_pytorch_weights(model, get_default_weights_path(), strict=False)
            model.eval()
            self._model = model
        return self._model

    def transcribe(self, audio_path: Path) -> tuple[list[DrumEvent], TranscriberInfo]:
        import torch
        from adtof_pytorch import LABELS_5, load_audio_for_model
        from adtof_pytorch.post_processing import NotePeakPickingProcessor

        model = self._load_model()
        features = load_audio_for_model(str(audio_path))
        with torch.no_grad():
            activations = model(features).cpu().numpy()[0]  # (frames, classes)

        events: list[DrumEvent] = []
        for index, label in enumerate(LABELS_5):
            column = activations[:, index]
            picker = NotePeakPickingProcessor(
                threshold=self.thresholds[LABEL_TO_INSTRUMENT[label]], fps=FPS, **PEAK_PICKING
            )
            for time_sec, _ in picker.process(column):
                frame = min(len(column) - 1, int(round(time_sec * FPS)))
                strength = float(np.clip(column[frame], 0.0, 1.0))
                events.append(
                    DrumEvent(
                        round(float(time_sec), 4), LABEL_TO_INSTRUMENT[label], round(strength, 4)
                    )
                )
        order = list(LABEL_TO_INSTRUMENT.values())
        events.sort(key=lambda e: (e.time_sec, order.index(e.instrument)))

        info = TranscriberInfo(
            method="adtof-pytorch",
            version=f"{version('adtof-pytorch')}+{ADTOF_COMMIT[:7]}",
            params={
                "thresholds": dict(self.thresholds),
                "fps": FPS,
                "peak_picking": PEAK_PICKING,
            },
            device="cpu",
        )
        return events, info
