import pytest

from poc.recording.calibration import Calibration
from poc.recording.note_map import load_note_map
from poc.recording.taps import taps_to_groundtruth

SHIFT_SEC = 2.03
CALIBRATION = Calibration(
    offsets_ms={"kick": -2.0, "snare": -3.0, "hihat": -4.0},
    note_offsets_ms={36: -2.0, 42: -4.0, 44: -5.0},
    std_ms={"kick": 0.3, "snare": 0.3, "hihat": 0.3},
    counts={"kick": 8, "snare": 8, "hihat": 8},
    outliers=0,
)
BEAT = 0.5


def tapped(n_beats=24, missing=(), extra=(), pedal=False):
    """MIDI notes for hi-hat taps on every beat and a kick on every 4th beat, in recording time."""
    notes = []
    for i in range(n_beats):
        if i in missing:
            continue
        t = SHIFT_SEC + 1.0 + i * BEAT
        notes.append({"time_sec": t + 0.004, "note": 44 if pedal else 42, "velocity": 80})
        if i % 4 == 0:
            notes.append({"time_sec": t + 0.012, "note": 36, "velocity": 90})
    for t in extra:
        notes.append({"time_sec": SHIFT_SEC + t, "note": 42, "velocity": 80})
    return sorted(notes, key=lambda n: n["time_sec"])


def convert(notes):
    return taps_to_groundtruth(
        notes, load_note_map(), CALIBRATION, "cal-1", SHIFT_SEC, "run-a", duration_sec=60.0
    )


def test_hihat_taps_are_beats_and_kicks_mark_downbeats():
    gt = convert(tapped())
    assert gt.source == "td17_taps"
    assert len(gt.beats) == 24
    assert gt.beats[0] == pytest.approx(1.0, abs=1e-6)  # 1.004 - 0.004 calibration
    assert gt.downbeats == pytest.approx([1.0 + i * BEAT for i in range(0, 24, 4)], abs=1e-6)
    assert gt.regions == [(gt.beats[0], gt.beats[-1])]
    assert gt.alignment["calibration_id"] == "cal-1"
    assert gt.warnings == []


def test_pedal_taps_count_as_beats():
    gt = convert(tapped(pedal=True))
    assert len(gt.beats) == 24
    assert gt.beats[0] == pytest.approx(0.999, abs=1e-6)  # pedal offset -5 ms


def test_double_triggers_are_dropped():
    notes = tapped()
    notes.append({"time_sec": notes[0]["time_sec"] + 0.02, "note": 42, "velocity": 40})
    gt = convert(sorted(notes, key=lambda n: n["time_sec"]))
    assert len(gt.beats) == 24


def test_missed_and_extra_taps_are_reported():
    gt = convert(tapped(missing=(10,), extra=(1.0 + 15.25 * BEAT,)))
    codes = [(w.code, round(w.value, 2)) for w in gt.warnings]
    assert ("tap_interval", 5.5) in codes  # the gap where beat 10 is missing starts at 5.5 s
    assert any(code == "tap_interval" and abs(v - 8.5) < 0.01 for code, v in codes)
