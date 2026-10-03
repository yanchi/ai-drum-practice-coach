import json

import numpy as np
import pytest
from conftest import synth_drums

from poc.recording.calibration import Calibration, CalibrationError, measure_calibration
from poc.recording.note_map import load_note_map

SR = 44100
DELAYS_MS = {36: 2.0, 38: -22.0, 40: -21.0, 42: -20.0, 46: -20.5, 44: -19.0}
INSTRUMENT = {36: "kick", 38: "snare", 40: "snare", 42: "hihat", 46: "hihat", 44: "hihat"}


def session(notes=(36, 38, 40, 42, 46, 44), per_note=8, jitter_ms=0.2, seed=0):
    """Pads hit one at a time, 1 s apart. Audio sounds DELAYS_MS after each MIDI time."""
    rng = np.random.default_rng(seed)
    midi, hits, t = [], [], 1.0
    for note in notes:
        for _ in range(per_note):
            midi.append({"time_sec": t, "note": note, "velocity": 90})
            delay = (DELAYS_MS[note] + rng.uniform(-jitter_ms, jitter_ms)) / 1000
            hits.append((t + delay, INSTRUMENT[note], 90))
            t += 1.0
    return synth_drums(hits, t + 1, SR, channels=2), midi


def test_measures_offsets_per_instrument_and_note():
    audio, midi = session()
    cal = measure_calibration(audio, SR, midi, load_note_map())

    # The onset is where the sound reaches 15% of its peak, so a slow 60 Hz kick reads
    # a few tenths of a millisecond late; the same holds for the real TD-17 sounds.
    assert cal.offsets_ms["kick"] == pytest.approx(2.0, abs=0.6)
    assert cal.offsets_ms["snare"] == pytest.approx(-21.5, abs=0.8)  # median of head and rim
    assert cal.note_offsets_ms[38] == pytest.approx(-22.0, abs=0.3)
    assert cal.note_offsets_ms[40] == pytest.approx(-21.0, abs=0.3)
    assert cal.note_offsets_ms[44] == pytest.approx(-19.0, abs=0.3)
    assert max(cal.std_ms.values()) <= 0.5
    assert cal.counts["hihat"] == 24


def test_offset_for_prefers_the_note():
    audio, midi = session()
    cal = measure_calibration(audio, SR, midi, load_note_map())
    assert cal.offset_sec(40, "snare") == pytest.approx(-0.021, abs=0.0003)
    assert cal.offset_sec(37, "snare") == pytest.approx(cal.offsets_ms["snare"] / 1000)  # not hit


def test_round_trip(tmp_path):
    audio, midi = session()
    cal = measure_calibration(audio, SR, midi, load_note_map())
    path = tmp_path / "calibration.json"
    path.write_text(json.dumps(cal.to_dict()))
    assert Calibration.from_dict(json.loads(path.read_text())) == cal


def test_missing_instrument():
    audio, midi = session(notes=(36, 38, 40))
    with pytest.raises(CalibrationError, match="hihat"):
        measure_calibration(audio, SR, midi, load_note_map())


def test_too_much_jitter():
    audio, midi = session(jitter_ms=4.0)
    with pytest.raises(CalibrationError, match="std"):
        measure_calibration(audio, SR, midi, load_note_map())
