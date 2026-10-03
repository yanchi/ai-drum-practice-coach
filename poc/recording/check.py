"""`poc record --check`: loopback and pad note check on the TD-17 (research R-07, R-08)."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass

import numpy as np

from poc.recording.devices import find_audio_device, find_midi_port
from poc.recording.note_map import load_note_map, parse_note_on

SAMPLE_RATE = 44100
TEST_SEC = 5.0
MAX_LEVEL_DB = -40.0
MAX_CORRELATION = 0.1
MAX_LAG_SEC = 0.2


@dataclass(frozen=True)
class LoopbackResult:
    level_db: float  # recorded RMS relative to the played signal
    correlation: float  # max normalized cross-correlation within ±MAX_LAG_SEC
    passed: bool


def loopback_metrics(
    played: np.ndarray, recorded: np.ndarray, sr: int = SAMPLE_RATE
) -> LoopbackResult:
    """Does the recording contain what was played? Arrays are (channels, samples)."""
    p = played.mean(axis=0).astype(np.float64)
    r = recorded.mean(axis=0).astype(np.float64)
    n = min(len(p), len(r))
    p, r = p[:n], r[:n]
    rms_p = np.sqrt(np.mean(p**2)) + 1e-12
    rms_r = np.sqrt(np.mean(r**2)) + 1e-12
    level_db = float(20 * np.log10(rms_r / rms_p))
    size = 1 << int(np.ceil(np.log2(2 * n)))
    corr = np.fft.irfft(np.fft.rfft(r, size) * np.conj(np.fft.rfft(p, size)), size)
    max_lag = min(int(MAX_LAG_SEC * sr), n - 1)
    window = np.concatenate([corr[: max_lag + 1], corr[size - max_lag :]])
    correlation = float(np.max(np.abs(window)) / (np.linalg.norm(p) * np.linalg.norm(r) + 1e-12))
    passed = level_db <= MAX_LEVEL_DB and correlation < MAX_CORRELATION
    return LoopbackResult(level_db, correlation, passed)


def _loopback_test(device: dict) -> LoopbackResult:
    import sounddevice as sd

    rng = np.random.default_rng(0)
    played = (0.1 * rng.standard_normal((int(TEST_SEC * SAMPLE_RATE), 2))).astype(np.float32)
    recorded = sd.playrec(
        played,
        samplerate=SAMPLE_RATE,
        channels=2,
        dtype="float32",
        device=(device["index"], device["index"]),
        blocking=True,
    )
    return loopback_metrics(played.T, recorded.T)


def _pad_test(port_index: int, device: dict, seconds: float) -> tuple[dict[int, int], float]:
    """Print each received note and return (note counts, peak level of the drum audio in dBFS).

    The audio is recorded at the same time to confirm that the USB audio input works
    (macOS returns silence when the app has no microphone permission)."""
    import rtmidi
    import sounddevice as sd

    note_map = load_note_map()
    seen: dict[int, int] = {}
    midi_in = rtmidi.MidiIn()
    midi_in.open_port(port_index)
    print(
        f"Hit each pad once (kick, snare head / rim, hihat open / closed / pedal, toms, "
        f"cymbals) within {seconds:.0f} s...",
        file=sys.stderr,
    )
    peak = 0.0

    def audio_callback(indata, frames, time_info, status):
        nonlocal peak
        peak = max(peak, float(np.max(np.abs(indata))))

    stream = sd.InputStream(
        device=device["index"], samplerate=SAMPLE_RATE, channels=2, callback=audio_callback
    )
    deadline = time.monotonic() + seconds
    try:
        stream.start()
        while time.monotonic() < deadline:
            event = midi_in.get_message()
            if event is None:
                time.sleep(0.002)
                continue
            parsed = parse_note_on(event[0])
            if parsed is None:
                continue
            note, velocity = parsed
            seen[note] = seen.get(note, 0) + 1
            if not note_map.is_known(note):
                label = "UNKNOWN (add it to td17_note_map.yaml)"
            else:
                label = note_map.instrument_for(note) or "ignored (tom / cymbal)"
            print(f"  note {note:3d} velocity {velocity:3d} -> {label}", file=sys.stderr)
    finally:
        stream.stop()
        stream.close()
        midi_in.close_port()
    return seen, float(20 * np.log10(peak + 1e-12))


def run_check(device_name: str, midi_port_name: str, pad_seconds: float = 30.0) -> bool:
    device = find_audio_device(device_name)
    port_index = find_midi_port(midi_port_name)

    print(
        f"[1/2] Loopback test on {device['name']}: playing noise for {TEST_SEC:.0f} s. "
        "Do not hit any pad.",
        file=sys.stderr,
    )
    loopback = _loopback_test(device)
    status = "PASS" if loopback.passed else "FAIL"
    print(
        f"  recorded level {loopback.level_db:.1f} dB (≤ {MAX_LEVEL_DB:g}), "
        f"correlation {loopback.correlation:.3f} (< {MAX_CORRELATION:g}) -> {status}"
    )
    if not loopback.passed:
        print(
            "  The recording contains the played audio. Check the TD-17 USB audio "
            "settings (loopback / USB audio routing) before recording."
        )

    print("[2/2] Pad check", file=sys.stderr)
    seen, peak_db = _pad_test(port_index, device, pad_seconds)
    note_map = load_note_map()
    found = {note_map.instrument_for(n) for n in seen} - {None}
    missing = [i for i in ("kick", "snare", "hihat") if i not in found]
    unknown = [n for n in seen if not note_map.is_known(n)]
    print(f"  notes received: {sorted(seen)}; evaluated instruments seen: {sorted(found)}")
    if missing:
        print(f"  not hit: {', '.join(missing)}")
    if unknown:
        print(f"  unknown notes: {unknown} (add them to poc/recording/td17_note_map.yaml)")
    audio_ok = peak_db > -60.0
    print(f"  drum audio peak {peak_db:.1f} dBFS -> {'OK' if audio_ok else 'NO AUDIO'}")
    if not audio_ok and seen:
        print(
            "  MIDI arrived but no audio was recorded. Allow microphone access for this app "
            "(System Settings > Privacy & Security > Microphone) and check the TD-17 USB "
            "audio output level."
        )
    pads_ok = not missing and not unknown and audio_ok
    passed = loopback.passed and pads_ok
    print(f"result={'PASS' if passed else 'FAIL'}")
    return passed
