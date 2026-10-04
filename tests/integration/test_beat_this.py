import numpy as np
import pytest
from conftest import synth_drums

from poc.beat.beat_this_adapter import detect_beats

pytestmark = pytest.mark.slow

SR = 44100
BPM = 120


def test_beat_this_follows_synthetic_eight_beat():
    beat = 60 / BPM
    hits = []
    for i in range(int(30 / (beat / 2)) - 2):
        t = 0.5 + i * beat / 2
        hits.append((t, "hihat", 90))
        if i % 4 == 0:
            hits.append((t, "kick", 110))
        if i % 4 == 2:
            hits.append((t, "snare", 110))
    audio = synth_drums(hits, 30, SR)[0]  # mono

    beats, downbeats = detect_beats(audio, SR)

    intervals = np.diff(beats)
    assert np.median(intervals) == pytest.approx(beat, abs=0.02)
    on_grid = [b for b in beats if abs((b - 0.5) / beat - round((b - 0.5) / beat)) * beat < 0.04]
    assert len(on_grid) / len(beats) >= 0.9
    assert len(downbeats) >= 1
