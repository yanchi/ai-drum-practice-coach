import pytest

from poc.domain import DrumEvent, GroundTruth, GroundTruthHit
from poc.evaluation.matching import evaluate_events


def gt(hits, regions=((0.0, 100.0),)):
    return GroundTruth(
        source="td17_midi",
        target_kind="evaluation_mix",
        target_id="rec",
        regions=list(regions),
        hits=[GroundTruthHit(t, inst, vel, ghost) for t, inst, vel, ghost in hits],
    )


def ev(*items):
    return [DrumEvent(t, inst, s) for t, inst, s in items]


def test_perfect_match_and_timing():
    truth = gt([(1.0, "kick", 100, False), (2.0, "kick", 80, False)])
    result = evaluate_events(truth, ev((1.005, "kick", 0.9), (1.995, "kick", 0.7)))
    m = result.metrics["kick"]
    assert (m.tp, m.fp, m.fn) == (2, 0, 0)
    assert m.precision == m.recall == m.f1 == 1.0
    assert m.timing_ms["mae"] == pytest.approx(5.0)
    assert m.timing_ms["median_signed"] == pytest.approx(0.0, abs=1e-9)
    assert result.tp_errors_ms["kick"] == pytest.approx([5.0, -5.0])


def test_two_estimates_near_one_hit():
    result = evaluate_events(
        gt([(1.0, "snare", 90, False)]), ev((0.99, "snare", 0.5), (1.01, "snare", 0.5))
    )
    m = result.metrics["snare"]
    assert (m.tp, m.fp, m.fn) == (1, 1, 0)


def test_one_estimate_between_two_hits():
    truth = gt([(1.0, "hihat", 80, False), (1.08, "hihat", 80, False)])
    m = evaluate_events(truth, ev((1.04, "hihat", 0.5))).metrics["hihat"]
    assert (m.tp, m.fp, m.fn) == (1, 0, 1)


def test_global_assignment_beats_greedy():
    # Greedy nearest-first would pair the estimate at 1.03 with the hit at 1.04 and leave
    # the hit at 1.00 unmatched; the optimal one-to-one assignment matches both.
    truth = gt([(1.00, "kick", 90, False), (1.04, "kick", 90, False)])
    m = evaluate_events(truth, ev((1.03, "kick", 0.5), (1.08, "kick", 0.5))).metrics["kick"]
    assert m.tp == 2


def test_outside_tolerance():
    m = evaluate_events(gt([(1.0, "kick", 90, False)]), ev((1.06, "kick", 0.5))).metrics["kick"]
    assert (m.tp, m.fp, m.fn) == (0, 1, 1)
    assert m.precision == 0.0 and m.recall == 0.0 and m.f1 == 0.0
    assert m.timing_ms["mae"] is None


def test_instruments_are_separate():
    m = evaluate_events(gt([(1.0, "kick", 90, False)]), ev((1.0, "snare", 0.5))).metrics
    assert (m["kick"].fn, m["snare"].fp) == (1, 1)


def test_ghost_notes_are_reported_separately():
    truth = gt([(1.0, "snare", 90, False), (1.2, "snare", 20, True), (1.4, "snare", 20, True)])
    result = evaluate_events(truth, ev((1.0, "snare", 0.8), (1.2, "snare", 0.1)))
    m = result.metrics["snare"]
    assert (m.tp, m.fp, m.fn) == (1, 0, 0)  # the detected ghost is neither TP nor FP
    assert result.ghost_notes["snare"] == {"detected": 1, "total": 2}


def test_regions_and_other_instruments_are_ignored():
    truth = gt([(1.0, "kick", 90, False)], regions=[(0.5, 1.5)])
    result = evaluate_events(truth, ev((1.0, "kick", 0.5), (3.0, "kick", 0.5), (1.0, "tom", 0.5)))
    m = result.metrics["kick"]
    assert (m.tp, m.fp) == (1, 0)


def test_empty_counts_give_none():
    m = evaluate_events(gt([]), []).metrics["kick"]
    assert m.precision is None and m.recall is None and m.f1 is None


def test_strength_spearman():
    hits = [(float(i), "kick", 20 + 10 * i, False) for i in range(6)]
    events = ev(*[(float(i), "kick", 0.1 * i) for i in range(6)])
    assert evaluate_events(gt(hits), events).metrics["kick"].strength_spearman == pytest.approx(1.0)
    few = evaluate_events(gt(hits[:4]), events[:4]).metrics["kick"]
    assert few.strength_spearman is None  # fewer than 5 TP
    manual = evaluate_events(gt([(float(i), "kick", None, False) for i in range(6)]), events)
    assert manual.metrics["kick"].strength_spearman is None
