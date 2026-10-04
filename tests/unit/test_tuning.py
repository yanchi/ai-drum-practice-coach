import pytest

from poc.domain import DrumEvent, GroundTruth, GroundTruthHit
from poc.errors import UserInputError
from poc.evaluation.tuning import Song, report_markdown, tune

# Fake "activations": a list of (time, instrument, peak height). The fake peak picker keeps
# peaks at or above the threshold, so the best threshold separates real hits from noise.


def fake_events(activations, thresholds):
    return [
        DrumEvent(t, inst, h)
        for t, inst, h in activations
        if inst in thresholds and h >= thresholds[inst]
    ]


def song(key, real_height, noise_height):
    hits = [GroundTruthHit(float(i), "kick", 90, False) for i in range(1, 11)]
    activations = [(float(i), "kick", real_height) for i in range(1, 11)]
    activations += [(i + 0.5, "kick", noise_height) for i in range(1, 6)]  # 5 false peaks
    gt = GroundTruth("td17_midi", "evaluation_mix", key, [(0.0, 20.0)], hits)
    return Song(key=key, activations=activations, groundtruth=gt)


def test_tune_picks_threshold_between_noise_and_hits():
    songs = [song("a", 0.2, 0.1), song("b", 0.22, 0.09), song("c", 0.18, 0.08)]
    report = tune(songs, fake_events)["kick"]
    best = report["best_threshold_all_songs"]
    assert 0.1 < best <= 0.18
    assert report["leave_one_out"]["f1"] == pytest.approx(1.0)
    assert len(report["folds"]) == 3


def test_leave_one_out_is_honest():
    # Song "c" has weaker hits than the others; a threshold chosen on a and b misses them.
    songs = [song("a", 0.3, 0.2), song("b", 0.3, 0.2), song("c", 0.14, 0.06)]
    report = tune(songs, fake_events)["kick"]
    fold_c = next(f for f in report["folds"] if f["held_out"] == "c")
    assert fold_c["threshold"] > 0.2
    assert report["leave_one_out"]["fn"] == 10  # all hits of c are missed
    best_all_f1 = max(g["f1"] for g in report["grid"])
    assert report["leave_one_out"]["f1"] < best_all_f1


def test_needs_two_songs():
    with pytest.raises(UserInputError):
        tune([song("a", 0.2, 0.1)], fake_events)


def test_markdown():
    text = report_markdown(tune([song("a", 0.2, 0.1), song("b", 0.2, 0.1)], fake_events))
    assert "## kick" in text and "Leave-one-out F1" in text
