"""Boundary between the pipeline and a drum transcription model."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from poc.domain import DrumEvent, TranscriberInfo


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path) -> tuple[list[DrumEvent], TranscriberInfo]: ...
