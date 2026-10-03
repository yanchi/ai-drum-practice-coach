"""Evaluation mix and ground truth from a TD-17 play-along (research R-06, R-10)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from poc.audio.signal import fit_length, match_channels, resample
from poc.domain import GroundTruth, GroundTruthHit, MidiAudioAlignment
from poc.errors import UserInputError
from poc.recording.calibration import Calibration
from poc.recording.note_map import NoteMap, drop_double_triggers

SAMPLE_RATE = 44100
REGION_MARGIN_SEC = 0.5
# Only the snare has ghost notes: light hi-hat strokes are normal timekeeping and are scored
# (2026-10-04 review; the developer's hi-hat median velocity was 38).
GHOST_INSTRUMENTS = ("snare",)


def _rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))


def drum_gain(drums: np.ndarray, accompaniment: np.ndarray, target_db: float) -> float:
    """Gain g so that g * drums sits `target_db` below the mix (drums and accompaniment
    are treated as uncorrelated): g = r * rms_a / (rms_d * sqrt(1 - r^2))."""
    r = 10 ** (target_db / 20)
    rms_d, rms_a = _rms(drums), _rms(accompaniment)
    if rms_d < 1e-6:
        raise UserInputError("the drum recording is silent")
    if not 0 < r < 1:
        raise UserInputError(f"invalid target drum level {target_db} dB")
    return r * rms_a / (rms_d * np.sqrt(1 - r * r))


def build_evaluation_mix(
    recording_dir: Path,
    poc1_run_dir: Path,
    calibration_id: str,
    calibration: Calibration,
    note_map: NoteMap,
    ghost_velocity: int = 40,
) -> tuple[Path, GroundTruth]:
    """Write `mix.wav` (accompaniment + drums at the original's drum level) and
    `groundtruth.json` (MIDI hits on the mix timeline) into the recording directory."""
    recording_dir, poc1_run_dir = Path(recording_dir), Path(poc1_run_dir)
    recording = json.loads((recording_dir / "recording.json").read_text())
    notes = json.loads((recording_dir / "midi_notes.json").read_text())
    run = json.loads((poc1_run_dir / "run.json").read_text())

    drums, sr = sf.read(recording_dir / "drums.wav", dtype="float32", always_2d=True)
    if sr != SAMPLE_RATE:
        raise UserInputError(f"recording must be {SAMPLE_RATE} Hz, got {sr}")
    accompaniment, acc_sr = sf.read(
        poc1_run_dir / "accompaniment.wav", dtype="float32", always_2d=True
    )
    accompaniment = match_channels(resample(accompaniment.T, acc_sr, SAMPLE_RATE), 2)
    length = accompaniment.shape[1]

    # Recorded frame j sounded together with playback frame j - latency (research R-05);
    # the accompaniment starts after the count-in.
    # Recordings made before the capture refactor kept the latencies under "device".
    device = recording["device"] if isinstance(recording.get("device"), dict) else recording
    latency_sec = device["input_latency_sec"] + device["output_latency_sec"]
    shift = recording["count_in_samples"] + int(round(latency_sec * SAMPLE_RATE))
    aligned = fit_length(match_channels(drums.T, 2)[:, shift:], length)

    target_db = next(s for s in run["stems"] if s["kind"] == "drums")["rms_db_relative_to_mix"]
    gain = drum_gain(aligned, accompaniment, target_db)
    mix = (accompaniment + gain * aligned).astype(np.float32)

    kept, dropped = drop_double_triggers(notes, note_map)
    hits, offsets_used = [], {}
    for note in kept:
        instrument = note_map.instrument_for(note["note"])
        if instrument is None:
            continue
        offset = calibration.offset_sec(note["note"], instrument)
        offsets_used[note["note"]] = round(offset * 1000, 3)
        time_sec = note["time_sec"] + offset - shift / SAMPLE_RATE
        if not 0 <= time_sec < length / SAMPLE_RATE:
            continue
        ghost = instrument in GHOST_INSTRUMENTS and note["velocity"] < ghost_velocity
        hits.append(GroundTruthHit(round(time_sec, 6), instrument, note["velocity"], ghost))
    if not hits:
        raise UserInputError(f"no kick / snare / hihat notes in {recording_dir}")
    hits.sort(key=lambda h: h.time_sec)
    duration = length / SAMPLE_RATE
    region = (
        round(max(0.0, hits[0].time_sec - REGION_MARGIN_SEC), 6),
        round(min(duration, hits[-1].time_sec + REGION_MARGIN_SEC), 6),
    )
    groundtruth = GroundTruth(
        source="td17_midi",
        target_kind="evaluation_mix",
        target_id=recording["recording_id"],
        regions=[region],
        hits=hits,
        alignment=MidiAudioAlignment(
            calibration_id=calibration_id,
            note_offsets_ms=offsets_used,
            max_std_ms=max(calibration.std_ms.values()),
            dropped_double_triggers=dropped,
            stream_latency_ms=round(latency_sec * 1000, 3),
            drum_gain_db=round(float(20 * np.log10(gain)), 3),
        ),
    )
    mix_path = recording_dir / "mix.wav"
    sf.write(mix_path, mix.T, SAMPLE_RATE, subtype="FLOAT")
    (recording_dir / "groundtruth.json").write_text(
        json.dumps(groundtruth.to_dict(), indent=1) + "\n"
    )
    return mix_path, groundtruth


def load_calibration(
    calibrations_dir: Path, calibration_dir: Path | None = None
) -> tuple[str, Calibration]:
    """The given calibration, or the newest one with a calibration.json."""
    if calibration_dir is None:
        candidates = sorted(Path(calibrations_dir).glob("*/calibration.json"))
        if not candidates:
            raise UserInputError(
                f"no calibration found in {calibrations_dir}; run `poc record --calibrate` first"
            )
        path = candidates[-1]
    else:
        path = Path(calibration_dir) / "calibration.json"
        if not path.exists():
            raise UserInputError(f"calibration.json not found in {calibration_dir}")
    return path.parent.name, Calibration.from_dict(json.loads(path.read_text()))
