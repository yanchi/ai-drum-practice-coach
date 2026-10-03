"""Listening aids for drum events: clicks over the original and a MIDI file (research R-14)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from poc.domain import DrumEvent

# Woodblock-like clicks: easy to tell apart from the drums. tom / cymbal: no click.
CLICK_FREQS = {"kick": 400.0, "snare": 800.0, "hihat": 1600.0}
CLICK_SEC = 0.06
ATTACK_SEC = 0.001
DECAY_SEC = 0.012  # time constant of the exponential decay
OVERTONE_RATIO = 2.76  # inharmonic partial typical of wooden percussion
ORIGINAL_GAIN = 10 ** (-6 / 20)
GM_DRUM_NOTES = {"kick": 36, "snare": 38, "hihat": 42, "tom": 47, "cymbal": 49}


def _click(freq: float, sr: int) -> np.ndarray:
    """A short woodblock-like "tok": fundamental + quieter inharmonic partial, fast decay."""
    t = np.arange(int(CLICK_SEC * sr)) / sr
    envelope = np.exp(-t / DECAY_SEC) * np.minimum(1.0, t / ATTACK_SEC)
    tone = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * OVERTONE_RATIO * t)
    return (tone * envelope / 1.35).astype(np.float32)


def render_check_wav(original: np.ndarray, sr: int, events: list[DrumEvent]) -> np.ndarray:
    """Original (at -6 dB) plus a click per kick / snare / hihat event, louder for stronger hits."""
    out = (original * ORIGINAL_GAIN).astype(np.float32)
    clicks = {inst: _click(freq, sr) for inst, freq in CLICK_FREQS.items()}
    length = out.shape[1]
    for event in events:
        click = clicks.get(event.instrument)
        if click is None:
            continue
        start = int(round(event.time_sec * sr))
        stop = min(length, start + len(click))
        if 0 <= start < length:
            out[:, start:stop] += (0.3 + 0.5 * event.strength) * click[: stop - start]
    return out


def write_events_midi(events: list[DrumEvent], path: Path) -> None:
    import pretty_midi

    midi = pretty_midi.PrettyMIDI()
    drums = pretty_midi.Instrument(program=0, is_drum=True, name="drums")
    for event in events:
        velocity = max(1, min(127, round(event.strength * 127)))
        drums.notes.append(
            pretty_midi.Note(
                velocity=velocity,
                pitch=GM_DRUM_NOTES[event.instrument],
                start=event.time_sec,
                end=event.time_sec + 0.1,
            )
        )
    midi.instruments.append(drums)
    midi.write(str(path))
