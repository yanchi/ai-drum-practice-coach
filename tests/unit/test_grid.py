import numpy as np
import pytest
from conftest import downbeat_activation, synthetic_beats

from poc.beat.grid import (
    bpm_overall,
    bpm_sections,
    choose_downbeats,
    estimate_meter,
    fill_gaps,
    find_gaps,
    regularize_downbeats,
)


def test_fill_gaps_follows_tempo_drift_and_flags_inferred():
    # 160 -> 175 BPM over 64 beats, with single beats missing early and late
    intervals = np.linspace(60 / 160, 60 / 175, 64)
    beats = list(np.round(np.concatenate([[0.0], np.cumsum(intervals)]), 4))
    missing = [5, 58]
    observed = [t for i, t in enumerate(beats) if i not in missing]
    times, inferred = fill_gaps(observed)
    assert len(times) == len(beats)
    assert times == pytest.approx(beats, abs=0.01)
    assert [i for i, flag in enumerate(inferred) if flag] == missing


def test_fill_gaps_fills_a_long_half_tempo_stretch():
    beats = synthetic_beats(180, 40)
    observed = beats[:40:2] + beats[40:]  # tracked at half tempo for the first 40 beats
    times, inferred = fill_gaps(observed)
    assert times == pytest.approx(beats, abs=0.002)
    assert sum(inferred) == 20


def test_fill_gaps_leaves_long_gaps():
    beats = synthetic_beats(120, 10) + synthetic_beats(120, 20, start=15)  # 5 s break
    times, inferred = fill_gaps(beats)
    assert times == beats
    assert not any(inferred)
    assert find_gaps(times) == [(beats[len(synthetic_beats(120, 10)) - 1], 15.0)]


def test_regularize_clean_activation():
    activation = downbeat_activation(32, phase=1)  # downbeats at beats 3, 7, 11, ...
    downbeats, changes = regularize_downbeats(activation)
    assert downbeats == list(range(3, 32, 4))
    assert changes == []


def test_regularize_follows_a_lasting_two_beat_shift():
    activation = downbeat_activation(96, phase=0, flips=[(40, 2)])  # WORKING MAN case
    downbeats, changes = regularize_downbeats(activation)
    assert downbeats[:10] == list(range(0, 40, 4))
    assert all((i + 2) % 4 == 0 for i in downbeats if i >= 40)
    assert len(changes) == 1 and 38 <= changes[0] <= 42


def test_regularize_ignores_isolated_spurious_peaks():
    activation = downbeat_activation(64, phase=0)
    activation[22] = 0.95  # one bar-1-like peak on beat 3 of a bar (PLASTIC BOMB case)
    activation[41] = 0.9
    downbeats, changes = regularize_downbeats(activation)
    assert downbeats == list(range(0, 64, 4))
    assert changes == []


def test_regularize_handles_inferred_beats_without_activation():
    activation = downbeat_activation(32)
    activation[8] = None  # an inferred beat on a downbeat
    downbeats, _ = regularize_downbeats(activation)
    assert downbeats == list(range(0, 32, 4))


def test_choose_downbeats_keeps_raw_when_not_four_four():
    beats = synthetic_beats(120, 10)
    raw = beats[::3]  # 3/4
    result = choose_downbeats(beats, [0.9] * len(beats), raw, meter=3, regularize=True)
    assert result["downbeats"] == raw
    assert result["source"] == "raw"
    assert [w.code for w in result["warnings"]] == ["meter_not_four"]


def test_estimate_meter_bpm_and_sections():
    beats = synthetic_beats(120, 40.5, start=0.5)
    raw = beats[::4][:-3] + [beats[-3]]  # one odd bar at the end
    assert estimate_meter(beats, raw) == 4
    assert bpm_overall(beats) == pytest.approx(120, abs=0.1)
    sections = bpm_sections(beats, beats[::4], bars_per_section=4)
    assert len(sections) == 5
    assert all(s["bpm"] == pytest.approx(120, abs=0.1) for s in sections)
    assert sections[0]["start_sec"] == beats[0]


def test_bpm_overall_is_not_quantized_by_frames():
    true = synthetic_beats(190.6, 60)
    quantized = [round(t / 0.02) * 0.02 for t in true]  # 20 ms frames: intervals 0.30 / 0.32
    assert bpm_overall(quantized) == pytest.approx(190.6, rel=0.003)
    with_break = quantized[:80] + [t + 5.0 for t in quantized[80:]]
    assert bpm_overall(with_break) == pytest.approx(190.6, rel=0.003)
