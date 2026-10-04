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


# --- PoC 2: drum events (specs/002-drum-event-extraction/data-model.md) ---

Instrument = Literal["kick", "snare", "hihat", "tom", "cymbal"]
EVALUATED_INSTRUMENTS = ("kick", "snare", "hihat")
TranscriptionInputKind = Literal["drum_stem", "mix", "accompaniment"]


@dataclass(frozen=True)
class DrumEvent:
    time_sec: float
    instrument: Instrument
    strength: float  # 0-1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TranscriptionInput:
    kind: TranscriptionInputKind
    poc1_run_id: str
    audio_path: str
    audio_sha256: str
    duration_sec: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TranscriberInfo:
    method: str
    version: str
    params: dict[str, Any]
    device: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TranscriptionRun:
    transcription_id: str
    created_at: str
    input: TranscriptionInput
    transcriber: TranscriberInfo
    events: list[DrumEvent]
    warnings: list[RunWarning] = field(default_factory=list)
    timings_sec: dict[str, float] | None = None
    peak_memory: dict[str, int | None] | None = None
    environment: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for event in self.events:
            counts[event.instrument] = counts.get(event.instrument, 0) + 1
        return {
            "schema_version": SCHEMA_VERSION,
            "transcription_id": self.transcription_id,
            "created_at": self.created_at,
            "input": self.input.to_dict(),
            "transcriber": self.transcriber.to_dict(),
            "events": [e.to_dict() for e in self.events],
            "event_counts": counts,
            "timings_sec": self.timings_sec,
            "peak_memory": self.peak_memory,
            "environment": self.environment,
            "warnings": [w.to_dict() for w in self.warnings],
        }


@dataclass(frozen=True)
class GroundTruthHit:
    time_sec: float
    instrument: str  # one of EVALUATED_INSTRUMENTS
    velocity: int | None
    ghost: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MidiAudioAlignment:
    """How TD-17 MIDI times were turned into ground-truth times (research R-06, R-10)."""

    calibration_id: str
    note_offsets_ms: dict[int, float]  # MIDI time + offset = audio time, per note used
    max_std_ms: float  # calibration spread (SC-008)
    dropped_double_triggers: int
    stream_latency_ms: float
    drum_gain_db: float

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["note_offsets_ms"] = {str(k): v for k, v in self.note_offsets_ms.items()}
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MidiAudioAlignment:
        return cls(
            **{**data, "note_offsets_ms": {int(k): v for k, v in data["note_offsets_ms"].items()}}
        )


@dataclass(frozen=True)
class GroundTruth:
    source: Literal["td17_midi", "manual"]
    target_kind: Literal["evaluation_mix", "poc1_song"]
    target_id: str
    regions: list[tuple[float, float]]
    hits: list[GroundTruthHit]
    alignment: MidiAudioAlignment | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "source": self.source,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "regions": [list(r) for r in self.regions],
            "hits": [h.to_dict() for h in self.hits],
            "alignment": self.alignment.to_dict() if self.alignment else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GroundTruth:
        alignment = data.get("alignment")
        return cls(
            source=data["source"],
            target_kind=data["target_kind"],
            target_id=data["target_id"],
            regions=[(float(a), float(b)) for a, b in data["regions"]],
            hits=[GroundTruthHit(**h) for h in data["hits"]],
            alignment=MidiAudioAlignment.from_dict(alignment) if alignment else None,
        )


@dataclass(frozen=True)
class InstrumentMetrics:
    tp: int
    fp: int
    fn: int
    precision: float | None
    recall: float | None
    f1: float | None
    timing_ms: dict[str, float | None]  # mae / median_abs / p95_abs / median_signed
    strength_spearman: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --- PoC 3: beat grid and bar mapping (specs/003-beat-bar-mapping/data-model.md) ---

BeatInputKind = Literal["mix", "drum_stem"]
GRID_POSITIONS = ("0", "1/4", "1/3", "1/2", "2/3", "3/4")


@dataclass(frozen=True)
class Beat:
    time_sec: float
    inferred: bool = False  # filled in from the neighbouring intervals (research R-02)
    downbeat_activation: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BeatGrid:
    beatgrid_id: str
    created_at: str
    input: dict[str, Any]  # kind / poc1_run_id / audio_sha256 / duration_sec
    estimator: dict[str, Any]  # method / version / checkpoint / device
    beats: list[Beat]
    downbeats: list[float]  # used for mapping
    downbeats_raw: list[float]  # as estimated (offset applied)
    downbeat_source: Literal["regularized", "raw"]
    meter: int
    bpm: float
    bpm_sections: list[dict[str, float]] = field(default_factory=list)
    offset: dict[str, Any] = field(default_factory=dict)  # applied_ms / from_transcription_id
    regularization: dict[str, Any] = field(default_factory=dict)
    gaps: list[tuple[float, float]] = field(default_factory=list)
    warnings: list[RunWarning] = field(default_factory=list)
    timings_sec: dict[str, float] | None = None
    peak_memory: dict[str, int | None] | None = None
    environment: dict[str, str] | None = None

    @property
    def beat_times(self) -> list[float]:
        return [b.time_sec for b in self.beats]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "beatgrid_id": self.beatgrid_id,
            "created_at": self.created_at,
            "input": self.input,
            "estimator": self.estimator,
            "beats": [b.to_dict() for b in self.beats],
            "downbeats": self.downbeats,
            "downbeats_raw": self.downbeats_raw,
            "downbeat_source": self.downbeat_source,
            "meter": self.meter,
            "bpm": self.bpm,
            "bpm_sections": self.bpm_sections,
            "offset": self.offset,
            "regularization": self.regularization,
            "gaps": [list(g) for g in self.gaps],
            "warnings": [w.to_dict() for w in self.warnings],
            "timings_sec": self.timings_sec,
            "peak_memory": self.peak_memory,
            "environment": self.environment,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BeatGrid:
        return cls(
            beatgrid_id=data["beatgrid_id"],
            created_at=data["created_at"],
            input=data["input"],
            estimator=data["estimator"],
            beats=[Beat(**b) for b in data["beats"]],
            downbeats=data["downbeats"],
            downbeats_raw=data["downbeats_raw"],
            downbeat_source=data["downbeat_source"],
            meter=data["meter"],
            bpm=data["bpm"],
            bpm_sections=data.get("bpm_sections", []),
            offset=data.get("offset", {}),
            regularization=data.get("regularization", {}),
            gaps=[(float(a), float(b)) for a, b in data.get("gaps", [])],
            warnings=[RunWarning(**w) for w in data.get("warnings", [])],
            timings_sec=data.get("timings_sec"),
            peak_memory=data.get("peak_memory"),
            environment=data.get("environment"),
        )


@dataclass(frozen=True)
class BeatPosition:
    bar: int | None  # 1-based; 0 before the first downbeat; None where there are no beats
    beat: int | None  # 1-based beat in the bar
    position: float | None  # fraction of the beat before rounding, 0 <= position < 1
    grid: str | None  # one of GRID_POSITIONS
    deviation_ms: float | None  # from the grid position; negative = early
    unmapped_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReferencePerformance:
    reference_id: str
    created_at: str
    beatgrid_id: str
    transcription_id: str
    poc1_run_id: str
    events: list[tuple[DrumEvent, BeatPosition]]

    @property
    def bars(self) -> int:
        return max((p.bar for _, p in self.events if p.bar is not None), default=0)

    @property
    def unmapped_count(self) -> int:
        return sum(1 for _, p in self.events if p.bar is None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "reference_id": self.reference_id,
            "created_at": self.created_at,
            "beatgrid_id": self.beatgrid_id,
            "transcription_id": self.transcription_id,
            "poc1_run_id": self.poc1_run_id,
            "bars": self.bars,
            "unmapped_count": self.unmapped_count,
            "events": [{"event": e.to_dict(), "position": p.to_dict()} for e, p in self.events],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReferencePerformance:
        return cls(
            reference_id=data["reference_id"],
            created_at=data["created_at"],
            beatgrid_id=data["beatgrid_id"],
            transcription_id=data["transcription_id"],
            poc1_run_id=data["poc1_run_id"],
            events=[
                (DrumEvent(**item["event"]), BeatPosition(**item["position"]))
                for item in data["events"]
            ],
        )


@dataclass(frozen=True)
class BeatGroundTruth:
    source: Literal["td17_taps", "manual"]
    poc1_run_id: str
    regions: list[tuple[float, float]]
    beats: list[float]
    downbeats: list[float]  # subset of beats
    alignment: dict[str, Any] | None = None  # calibration used for taps
    warnings: list[RunWarning] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "source": self.source,
            "poc1_run_id": self.poc1_run_id,
            "regions": [list(r) for r in self.regions],
            "beats": self.beats,
            "downbeats": self.downbeats,
            "alignment": self.alignment,
            "warnings": [w.to_dict() for w in self.warnings],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BeatGroundTruth:
        return cls(
            source=data["source"],
            poc1_run_id=data["poc1_run_id"],
            regions=[(float(a), float(b)) for a, b in data["regions"]],
            beats=data["beats"],
            downbeats=data["downbeats"],
            alignment=data.get("alignment"),
            warnings=[RunWarning(**w) for w in data.get("warnings", [])],
        )


@dataclass(frozen=True)
class BeatMetrics:
    tp: int
    fp: int
    fn: int
    precision: float | None
    recall: float | None
    f_measure: float | None
    timing_ms: dict[str, float | None]  # median_abs / p95_abs / median_signed

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
