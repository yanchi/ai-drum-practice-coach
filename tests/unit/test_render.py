import numpy as np
import pretty_midi
import pytest

from poc.domain import DrumEvent
from poc.transcription.render import CLICK_FREQS, CLICK_SEC, render_check_wav, write_events_midi

SR = 44100


def dominant_freq(segment: np.ndarray, sr: int) -> float:
    spectrum = np.abs(np.fft.rfft(segment * np.hanning(len(segment)), n=1 << 16))
    return float(np.fft.rfftfreq(1 << 16, 1 / sr)[np.argmax(spectrum)])


@pytest.mark.parametrize("instrument", ["kick", "snare", "hihat"])
def test_click_position_and_pitch(instrument):
    original = np.zeros((2, SR * 2), dtype=np.float32)
    out = render_check_wav(original, SR, [DrumEvent(1.0, instrument, 1.0)])

    assert out.shape == original.shape
    assert out.dtype == np.float32
    start, length = SR, int(CLICK_SEC * SR)
    assert np.all(out[:, :start] == 0)
    assert np.all(out[:, start + length :] == 0)
    assert np.max(np.abs(out[0, start : start + length])) > 0.05
    freq = dominant_freq(out[0, start : start + length], SR)
    assert freq == pytest.approx(CLICK_FREQS[instrument], rel=0.1)


def test_tom_and_cymbal_are_silent():
    original = np.zeros((1, SR), dtype=np.float32)
    events = [DrumEvent(0.2, "tom", 1.0), DrumEvent(0.5, "cymbal", 1.0)]
    assert np.all(render_check_wav(original, SR, events) == 0)


def test_original_is_kept_and_quieter_click_for_weak_hits():
    original = np.full((1, SR), 0.1, dtype=np.float32)
    strong = render_check_wav(original, SR, [DrumEvent(0.5, "snare", 1.0)])
    weak = render_check_wav(original, SR, [DrumEvent(0.5, "snare", 0.1)])
    assert np.allclose(strong[0, :1000], weak[0, :1000])  # before the click: original only
    seg = slice(SR // 2, SR // 2 + int(CLICK_SEC * SR))
    assert np.max(np.abs(strong[0, seg])) > np.max(np.abs(weak[0, seg]))


def test_events_midi(tmp_path):
    events = [
        DrumEvent(0.5, "kick", 1.0),
        DrumEvent(0.5, "hihat", 0.5),
        DrumEvent(1.0, "snare", 0.0),
        DrumEvent(1.5, "tom", 0.8),
        DrumEvent(2.0, "cymbal", 0.3),
    ]
    path = tmp_path / "events.mid"
    write_events_midi(events, path)

    midi = pretty_midi.PrettyMIDI(str(path))
    assert len(midi.instruments) == 1 and midi.instruments[0].is_drum
    notes = sorted((round(n.start, 3), n.pitch, n.velocity) for n in midi.instruments[0].notes)
    assert notes == [(0.5, 36, 127), (0.5, 42, 64), (1.0, 38, 1), (1.5, 47, 102), (2.0, 49, 38)]
