"""`poc record`: play the accompaniment on the TD-17 while recording its drum audio and MIDI
(research R-05). Playback and capture share one duplex stream, so recorded frame k was
captured during the same callback in which playback frame k was sent."""

from __future__ import annotations

import json
import shutil
import signal
import sys
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

from poc.audio.signal import match_channels, resample
from poc.errors import PocError, UserInputError
from poc.recording.devices import find_audio_device, find_midi_port, midi_input_ports
from poc.recording.note_map import load_note_map, parse_note_on
from poc.transcription.render import _click
from poc.transcription.run import load_poc1_run

SAMPLE_RATE = 44100
BLOCK_SIZE = 256
COUNT_IN_BEATS = 4
COUNT_IN_BPM = 120
CLICK_GAIN = 0.3  # song beat clicks (`record --click`)
MIN_BEAT_RATIO = 0.6


def build_playback(
    accompaniment: np.ndarray, sr: int, beats: int = COUNT_IN_BEATS, bpm: float = COUNT_IN_BPM
) -> tuple[np.ndarray, int]:
    """Stereo playback buffer: a count-in click per beat, then the accompaniment.

    Returns (buffer, count-in length in samples).
    """
    beat = int(round(60 / bpm * sr))
    count_in = np.zeros((2, beat * beats), dtype=np.float32)
    click = 0.5 * _click(1600.0, sr)
    for i in range(beats):
        count_in[:, i * beat : i * beat + len(click)] += click
    body = match_channels(accompaniment.astype(np.float32), 2)
    return np.concatenate([count_in, body], axis=1), count_in.shape[1]


def add_beat_clicks(
    playback: np.ndarray,
    count_in: int,
    beats: list[float],
    downbeats: list[float],
    sr: int,
    gain: float = CLICK_GAIN,
) -> int:
    """Add a click per song beat (higher on downbeats) to the playback in place.

    A beat closer than MIN_BEAT_RATIO of the median interval to the previous clicked beat is
    skipped, so a beat tracker glitch does not sound as a flam. Returns the number of clicks."""
    if len(beats) < 2:
        return 0
    min_gap = MIN_BEAT_RATIO * float(np.median(np.diff(beats)))
    downbeat_set = {round(t, 3) for t in downbeats}
    accent, normal = gain * _click(1600.0, sr), gain * _click(1000.0, sr)
    clicks, last = 0, None
    for t in beats:
        if last is not None and t - last < min_gap:
            continue
        last = t
        click = accent if round(t, 3) in downbeat_set else normal
        start = count_in + int(round(t * sr))
        end = min(start + len(click), playback.shape[1])
        if start >= end:
            break
        playback[:, start:end] += click[: end - start]
        clicks += 1
    return clicks


@dataclass(frozen=True)
class ClockFit:
    """Linear map from the audio stream clock (PortAudio stream time) to seconds in the
    recorded audio."""

    slope: float
    intercept: float
    residual_std_ms: float

    def seconds_at(self, perf_time: float) -> float:
        return self.slope * perf_time + self.intercept


def fit_clock(callback_times: np.ndarray, frame_indices: np.ndarray, sr: int) -> ClockFit:
    """Fit audio position (s) = slope * stream time + intercept.

    `callback_times` are the ADC times of the first frame of each input buffer and
    `frame_indices` the position of that frame in the recording."""
    if len(callback_times) < 2:
        raise ValueError("need at least two callbacks to fit the clock")
    seconds = np.asarray(frame_indices, dtype=np.float64) / sr
    slope, intercept = np.polyfit(np.asarray(callback_times, dtype=np.float64), seconds, 1)
    residual = seconds - (slope * callback_times + intercept)
    return ClockFit(float(slope), float(intercept), float(np.std(residual) * 1000))


def _load_accompaniment(poc1_run_dir: Path) -> np.ndarray:
    path = Path(poc1_run_dir) / "accompaniment.wav"
    if not path.exists():
        raise UserInputError(f"accompaniment.wav not found in {poc1_run_dir}")
    audio, sr = sf.read(path, dtype="float32", always_2d=True)
    return resample(audio.T, sr, SAMPLE_RATE)


@dataclass
class Capture:
    audio: np.ndarray  # (2, samples) as recorded from the TD-17
    notes: list[dict]  # {"time_sec", "note", "velocity"}; time_sec = MIDI arrival in the audio
    clock_fit: ClockFit
    input_latency_sec: float
    output_latency_sec: float
    stopped_early: bool


def capture(playback: np.ndarray, device: dict, port_index: int, message: str) -> Capture:
    """Play `playback` on the device while recording its input and MIDI.

    Stops at the end of the playback, on Ctrl+C or SIGTERM."""
    import rtmidi
    import sounddevice as sd

    captured: list[np.ndarray] = []
    clock: list[tuple[float, int]] = []
    notes: list[tuple[float, int, int]] = []  # (stream time, note, velocity)
    position = 0
    done = threading.Event()
    stream = None

    def audio_callback(indata, outdata, frames, time_info, status):
        nonlocal position
        # ADC time of the first captured frame, on the same clock as stream.time.
        clock.append((time_info.inputBufferAdcTime, position))
        chunk = playback[:, position : position + frames].T
        outdata[: len(chunk)] = chunk
        outdata[len(chunk) :] = 0
        captured.append(indata.copy())
        position += frames
        if position >= playback.shape[1]:
            done.set()

    def midi_callback(event, data=None):
        # Timestamp with the audio stream clock. (rtmidi delta times on macOS were tested
        # and found unusable: 32 s of notes summed to 48 s.)
        parsed = parse_note_on(event[0])
        if parsed and stream is not None and stream.active:
            notes.append((stream.time, *parsed))

    stream = sd.Stream(
        device=(device["index"], device["index"]),
        samplerate=SAMPLE_RATE,
        blocksize=BLOCK_SIZE,
        latency="low",
        channels=2,
        dtype="float32",
        callback=audio_callback,
    )
    midi_in = rtmidi.MidiIn()
    midi_in.open_port(port_index)
    midi_in.set_callback(midi_callback)
    previous_sigterm = signal.signal(signal.SIGTERM, lambda *_: done.set())
    print(message, file=sys.stderr)
    try:
        with stream:
            while not done.wait(timeout=0.5):
                pass
    except KeyboardInterrupt:
        print("Stopped by Ctrl+C; saving what was recorded.", file=sys.stderr)
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
        midi_in.cancel_callback()
        midi_in.close_port()

    if len(clock) < 2:
        raise PocError("nothing was recorded")
    times, frames = np.array(clock).T
    fit = fit_clock(times, frames, SAMPLE_RATE)
    audio = np.concatenate(captured).T
    return Capture(
        audio=audio,
        notes=[
            {"time_sec": round(fit.seconds_at(t), 6), "note": note, "velocity": velocity}
            for t, note, velocity in notes
        ],
        clock_fit=fit,
        input_latency_sec=stream.latency[0],
        output_latency_sec=stream.latency[1],
        stopped_early=audio.shape[1] < playback.shape[1],
    )


def save_capture(
    result: Capture,
    output_dir: Path,
    recording_id: str,
    metadata: dict,
    extra_files: dict[str, str] | None = None,
    save_audio: bool = True,
) -> Path:
    """Write drums.wav, midi_notes.json and recording.json (+ extra text files) atomically."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    final_dir = output_dir / recording_id
    partial_dir = output_dir / f"{recording_id}.partial"
    partial_dir.mkdir()
    try:
        if save_audio:
            sf.write(partial_dir / "drums.wav", result.audio.T, SAMPLE_RATE, subtype="FLOAT")
        (partial_dir / "midi_notes.json").write_text(json.dumps(result.notes, indent=1) + "\n")
        record = {
            "schema_version": 1,
            "recording_id": recording_id,
            **metadata,
            "sample_rate": SAMPLE_RATE,
            "duration_sec": result.audio.shape[1] / SAMPLE_RATE,
            "stopped_early": result.stopped_early,
            "input_latency_sec": result.input_latency_sec,
            "output_latency_sec": result.output_latency_sec,
            "block_size": BLOCK_SIZE,
            "clock_fit": asdict(result.clock_fit),
            "note_count": len(result.notes),
        }
        (partial_dir / "recording.json").write_text(json.dumps(record, indent=2) + "\n")
        for name, text in (extra_files or {}).items():
            (partial_dir / name).write_text(text)
        partial_dir.rename(final_dir)
    except BaseException:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise
    return final_dir


def record_play_along(
    poc1_run_dir: Path,
    device_name: str,
    midi_port_name: str,
    output_dir: Path,
    max_seconds: float | None = None,
    click: bool = False,
    transcriptions_dir: Path = Path("output/transcriptions"),
) -> Path:
    """Record one play-along with the PoC 1 accompaniment. Returns the recording directory.

    With `click`, a click on every song beat (Beat This!, cached in <run>/beats.json) is
    played along, shifted onto the drums of the run's drum stem transcription. It goes to
    the playback only, like the accompaniment."""
    poc1_run_dir = Path(poc1_run_dir)
    run = load_poc1_run(poc1_run_dir)
    device = find_audio_device(device_name)
    port_index = find_midi_port(midi_port_name)
    playback, count_in = build_playback(_load_accompaniment(poc1_run_dir), SAMPLE_RATE)
    click_info = None
    if click:
        from poc.beat.beats import click_beats

        beats, downbeats, click_info = click_beats(poc1_run_dir, transcriptions_dir)
        click_info["clicks"] = add_beat_clicks(playback, count_in, beats, downbeats, SAMPLE_RATE)
        click_info["gain"] = CLICK_GAIN
    if max_seconds is not None:  # e.g. a short test recording
        playback = playback[:, : count_in + int(max_seconds * SAMPLE_RATE)]
    seconds = playback.shape[1] / SAMPLE_RATE
    result = capture(
        playback,
        device,
        port_index,
        f"Recording {seconds:.0f} s: count-in ({COUNT_IN_BEATS} clicks), then the song. "
        "Ctrl+C to stop early.",
    )
    now = datetime.now().astimezone()
    return save_capture(
        result,
        output_dir,
        f"{now:%Y%m%d-%H%M%S}_{run['run_id'].split('_')[-1]}",
        {
            "kind": "play_along",
            "poc1_run_id": run["run_id"],
            "recorded_at": now.isoformat(timespec="seconds"),
            "count_in_samples": count_in,
            "device": device["name"],
            "midi_port": midi_input_ports()[port_index],
            "note_map": load_note_map().to_dict(),
            "click": click_info,
        },
    )


def record_beat_taps(
    poc1_run_dir: Path,
    device_name: str,
    midi_port_name: str,
    output_dir: Path,
    calibrations_dir: Path = Path("output/recordings/calibrations"),
    max_seconds: float | None = None,
) -> Path:
    """Play the original song (no beat clicks) and record beats tapped on the TD-17
    (specs/003-beat-bar-mapping R-06). Saves the MIDI and beat_groundtruth.json, no audio."""
    from poc.audio.decode import load_song
    from poc.recording.mix import load_calibration
    from poc.recording.taps import taps_to_groundtruth

    poc1_run_dir = Path(poc1_run_dir)
    run = load_poc1_run(poc1_run_dir)
    calibration_id, calibration = load_calibration(calibrations_dir)
    device = find_audio_device(device_name)
    port_index = find_midi_port(midi_port_name)
    song, audio, _ = load_song(Path(run["song"]["path"]))
    playback, count_in = build_playback(
        resample(audio.astype(np.float32), song.sample_rate, SAMPLE_RATE), SAMPLE_RATE
    )
    if max_seconds is not None:
        playback = playback[:, : count_in + int(max_seconds * SAMPLE_RATE)]
    seconds = playback.shape[1] / SAMPLE_RATE
    result = capture(
        playback,
        device,
        port_index,
        f"Recording {seconds:.0f} s: count-in ({COUNT_IN_BEATS} clicks), then the song. "
        "Tap the hi-hat on every beat and add the kick on each downbeat. Ctrl+C to stop early.",
    )
    shift_sec = count_in / SAMPLE_RATE + result.input_latency_sec + result.output_latency_sec
    groundtruth = taps_to_groundtruth(
        result.notes,
        load_note_map(),
        calibration,
        calibration_id,
        shift_sec,
        run["run_id"],
        duration_sec=song.duration_sec,
    )
    for warning in groundtruth.warnings:
        print(f"warning: {warning.message}", file=sys.stderr)
    now = datetime.now().astimezone()
    return save_capture(
        result,
        output_dir,
        f"{now:%Y%m%d-%H%M%S}_taps_{run['run_id'].split('_')[-1]}",
        {
            "kind": "beat_taps",
            "poc1_run_id": run["run_id"],
            "recorded_at": now.isoformat(timespec="seconds"),
            "count_in_samples": count_in,
            "device": device["name"],
            "midi_port": midi_input_ports()[port_index],
            "note_map": load_note_map().to_dict(),
            "beats": len(groundtruth.beats),
            "downbeats": len(groundtruth.downbeats),
        },
        extra_files={"beat_groundtruth.json": json.dumps(groundtruth.to_dict(), indent=1) + "\n"},
        save_audio=False,
    )


CALIBRATION_BPM = 60
CALIBRATION_SCHEDULE = [  # (beats, what to hit) after the count-in, one hit per click
    (8, "Kick"),
    (8, "Snare head"),
    (4, "Snare rim"),
    (8, "HiHat closed (pedal down, hit the top)"),
    (4, "HiHat open (pedal up)"),
    (4, "HiHat pedal only (chick)"),
]


def calibration_playback(sr: int = SAMPLE_RATE) -> tuple[np.ndarray, int]:
    """A guide click every beat at CALIBRATION_BPM: count-in, then one click per hit.

    Returns (stereo buffer, count-in length in samples)."""
    beats = sum(n for n, _ in CALIBRATION_SCHEDULE)
    beat = int(round(60 / CALIBRATION_BPM * sr))
    silence = np.zeros((2, beat * beats), dtype=np.float32)
    playback, count_in = build_playback(silence, sr, beats=COUNT_IN_BEATS, bpm=CALIBRATION_BPM)
    click = 0.3 * _click(800.0, sr)
    for i in range(beats):
        start = count_in + i * beat
        playback[:, start : start + len(click)] += click
    return playback, count_in


def record_calibration(device_name: str, midi_port_name: str, output_dir: Path) -> Path:
    """Record pads hit one at a time with a guide click and measure the MIDI-to-audio latency
    per pad (research R-06). The recording is kept even if the measurement fails."""
    from poc.recording.calibration import CalibrationError, measure_calibration

    device = find_audio_device(device_name)
    port_index = find_midi_port(midi_port_name)
    playback, count_in = calibration_playback()
    lines, beat = [], COUNT_IN_BEATS
    for count, label in CALIBRATION_SCHEDULE:
        lines.append(f"  clicks {beat + 1}-{beat + count}: {label} x{count}")
        beat += count
    result = capture(
        playback,
        device,
        port_index,
        f"Calibration ({playback.shape[1] / SAMPLE_RATE:.0f} s). After {COUNT_IN_BEATS} count-in "
        "clicks, hit one pad per click:\n" + "\n".join(lines),
    )
    note_map = load_note_map()
    try:
        calibration = measure_calibration(result.audio, SAMPLE_RATE, result.notes, note_map)
        extra = {"calibration.json": json.dumps(calibration.to_dict(), indent=2) + "\n"}
        error = None
    except CalibrationError as exc:
        extra, error = {}, exc
    now = datetime.now().astimezone()
    out = save_capture(
        result,
        output_dir,
        f"{now:%Y%m%d-%H%M%S}_calibration",
        {
            "kind": "calibration",
            "recorded_at": now.isoformat(timespec="seconds"),
            "count_in_samples": count_in,
            "device": device["name"],
            "midi_port": midi_input_ports()[port_index],
            "note_map": note_map.to_dict(),
        },
        extra,
    )
    if error is not None:
        raise CalibrationError(f"{error} (recording kept in {out})")
    return out
