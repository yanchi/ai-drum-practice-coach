import pytest
from conftest import synth_drums, write_wav

from poc.transcription.adtof_adapter import AdtofTranscriber

pytestmark = pytest.mark.slow

SR = 44100
BPM = 100


def eight_beat(sec: float):
    beat = 60 / BPM
    hits = []
    t, i = 0.5, 0
    while t < sec - 0.5:
        hits.append((t, "hihat", 90))
        if i % 4 == 0:
            hits.append((t, "kick", 110))
        if i % 4 == 2:
            hits.append((t, "snare", 110))
        t += beat / 2
        i += 1
    return hits


def test_adtof_detects_synthetic_pattern(tmp_path):
    hits = eight_beat(20)
    path = write_wav(tmp_path, "drums.wav", synth_drums(hits, 20, SR), SR, subtype="FLOAT")

    transcriber = AdtofTranscriber()
    events, info = transcriber.transcribe(path)

    assert info.method == "adtof-pytorch"
    assert info.device == "cpu"
    for instrument in ("kick", "snare", "hihat"):
        truth = [t for t, inst, _ in hits if inst == instrument]
        found = [e.time_sec for e in events if e.instrument == instrument]
        detected = sum(any(abs(f - t) <= 0.05 for f in found) for t in truth)
        assert detected / len(truth) >= 0.7, (instrument, detected, len(truth))
    assert all(0.0 <= e.strength <= 1.0 for e in events)

    again, _ = AdtofTranscriber().transcribe(path)
    assert again == events
