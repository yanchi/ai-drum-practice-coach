import pytest
from conftest import synthetic_beats

from poc.domain import BeatGroundTruth
from poc.evaluation.beats_eval import evaluate_grid, mapping_accuracy, tap_jitter

TRUE = synthetic_beats(120, 30.5, start=1.0)  # 0.5 s per beat, 60 beats
TRUE_DOWN = TRUE[::4]


def gt(region=(1.0, 30.0)):
    return BeatGroundTruth("td17_taps", "run-a", [region], TRUE, TRUE_DOWN)


def test_perfect_grid():
    result = evaluate_grid(TRUE, TRUE_DOWN, 120.0, 4, gt())
    assert result["beats"].f_measure == 1.0
    assert result["downbeats"].f_measure == 1.0
    assert result["bpm_error_pct"] == pytest.approx(0.0, abs=0.01)
    assert result["meter_match"] is True


def test_shifted_downbeats_and_tolerance():
    est_down = TRUE[2::4]  # every downbeat two beats late
    result = evaluate_grid([t + 0.05 for t in TRUE], [t + 0.05 for t in est_down], 121.0, 4, gt())
    assert result["beats"].f_measure == 1.0  # 50 ms is within 70 ms
    assert result["beats"].timing_ms["median_signed"] == pytest.approx(50)
    assert result["downbeats"].tp == 0
    assert result["bpm_error_pct"] == pytest.approx(100 / 120, abs=0.01)


def test_estimates_outside_the_region_are_ignored():
    result = evaluate_grid(TRUE, TRUE_DOWN, 120.0, 4, gt(region=(10.0, 20.0)))
    assert result["beats"].fp == 0 and result["beats"].fn == 0
    assert result["beats"].tp == 21


def test_mapping_accuracy_ignores_bar_numbering():
    events = [t + 0.25 for t in TRUE[8:40]] + TRUE[8:40]
    # the estimate has an extra bar at the start, so its bar numbers are all one higher
    est_beats = synthetic_beats(120, 1.0, start=-1.0) + TRUE
    est_down = [-1.0] + TRUE_DOWN
    mapping = mapping_accuracy(events, est_beats, est_down, gt())
    assert mapping["events"] == 64
    assert mapping["accuracy"] == 1.0


def test_mapping_accuracy_counts_wrong_downbeats():
    events = TRUE[8:40]
    mapping = mapping_accuracy(events, TRUE, TRUE[2::4], gt())
    assert mapping["matched_bar"] == 0
    assert mapping["accuracy"] == 0.0


def test_tap_jitter():
    taps = [t + 0.01 for t in TRUE]
    manual = BeatGroundTruth("manual", "run-a", [(5.0, 10.0)], TRUE, TRUE_DOWN)
    jitter = tap_jitter(taps, manual)
    assert jitter["count"] == 11
    assert jitter["median_abs"] == pytest.approx(10)
    assert jitter["p95_abs"] == pytest.approx(10)
