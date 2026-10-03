"""Domain model for the PoC (see specs/001-drum-stem-extraction/data-model.md).

This module must not depend on any ML library so that models can be replaced.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

SCHEMA_VERSION = 1

StemKind = Literal["drums", "accompaniment"]


@dataclass(frozen=True)
class Song:
    path: Path
    sha256: str
    format: str
    codec: str
    sample_rate: int
    channels: int
    num_samples: int

    @property
    def duration_sec(self) -> float:
        return self.num_samples / self.sample_rate

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "format": self.format,
            "codec": self.codec,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "num_samples": self.num_samples,
            "duration_sec": self.duration_sec,
        }


@dataclass(frozen=True)
class Stem:
    kind: StemKind
    path: Path  # relative to the run directory
    sample_rate: int
    channels: int
    num_samples: int
    peak: float
    rms_db_relative_to_mix: float

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "path": str(self.path)}


@dataclass(frozen=True)
class SeparatorInfo:
    method: str
    version: str
    model: str
    params: dict[str, Any]
    device: str
    model_samplerate: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AlignmentCheck:
    method: str
    window_start_sec: float
    lag_samples: int
    lag_ms: float
    length_match: bool
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunWarning:
    code: str
    message: str
    value: float | None = None
    threshold: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SeparationRun:
    run_id: str
    created_at: str
    status: Literal["succeeded", "failed"]
    song: Song
    separator: SeparatorInfo
    stems: list[Stem]
    alignment: AlignmentCheck
    warnings: list[RunWarning] = field(default_factory=list)
    timings_sec: dict[str, float] | None = None
    peak_memory: dict[str, int | None] | None = None
    environment: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "status": self.status,
            "song": self.song.to_dict(),
            "separator": self.separator.to_dict(),
            "stems": [s.to_dict() for s in self.stems],
            "alignment": self.alignment.to_dict(),
            "timings_sec": self.timings_sec,
            "peak_memory": self.peak_memory,
            "environment": self.environment,
            "warnings": [w.to_dict() for w in self.warnings],
        }


# Problems the developer can note for a stem: instruments that are missing or weak,
# "bleed" (other instruments leak in) and "artifacts" (audible degradation).
ISSUE_CHOICES = ("kick", "snare", "hihat", "toms", "cymbals", "bleed", "artifacts")
Verdict = Literal["ok", "ng"]


@dataclass(frozen=True)
class SeparationEvaluation:
    run_id: str
    song_label: str
    genre: str
    evaluated_at: str
    verdict: Verdict  # ok = usable for drum hit detection in PoC 2
    issues: list[str]
    notes: str = ""
