import json

import pytest

from poc.errors import UserInputError
from poc.evaluation.events_summary import summarize_events


def metrics(tp, fp, fn):
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": None,
        "recall": None,
        "f1": None,
        "timing_ms": {"median_abs": 3.0, "p95_abs": 8.0},
        "strength_spearman": None,
    }


def write_eval(root, eval_id, run_id, source, tp=9, fp=1, fn=1, error_ms=3.0, std=0.5, sec=5.0):
    tx_id = f"tx_{eval_id}"
    tx_dir = root / "transcriptions" / tx_id
    tx_dir.mkdir(parents=True)
    tx_dir.joinpath("transcription.json").write_text(
        json.dumps(
            {
                "input": {"kind": "drum_stem", "audio_sha256": "a", "duration_sec": 240.0},
                "transcriber": {"method": "m", "version": "v", "params": {}},
                "timings_sec": {"total": sec},
                "peak_memory": {"rss_bytes": 1},
                "environment": {"python": "3.11"},
                "warnings": [],
            }
        )
    )
    result = {
        "transcription_id": tx_id,
        "metrics": {i: metrics(tp, fp, fn) for i in ("kick", "snare", "hihat")},
        "tp_errors_ms": {i: [error_ms] * tp for i in ("kick", "snare", "hihat")},
        "ghost_notes": {i: {"detected": 1, "total": 2} for i in ("kick", "snare", "hihat")},
    }
    data = {
        "evaluation_id": eval_id,
        "poc1_run_id": run_id,
        "groundtruth": {
            "source": source,
            "alignment": {"max_std_ms": std} if source == "td17_midi" else None,
        },
        "results": {"drum_stem": result, "mix": result},
        "residual_drum_hits": {"counts": {"kick": 1, "snare": 0, "hihat": 2}}
        if source == "td17_midi"
        else None,
    }
    d = root / "evaluations" / eval_id
    d.mkdir(parents=True)
    d.joinpath("evaluation.json").write_text(json.dumps(data))


def status(criteria):
    return {c.criterion: c.status for c in criteria}


def summarize(root):
    return summarize_events(root / "evaluations", root / "reports")


def test_all_pass(tmp_path):
    for i in range(5):
        write_eval(tmp_path, f"e{i}", f"run{i}", "td17_midi")
    write_eval(tmp_path, "m0", "run0", "manual", tp=8, fp=1, fn=2)
    criteria, markdown = summarize(tmp_path)
    s = status(criteria)
    assert s == {
        k: "PASS" for k in ("SC-001", "SC-002", "SC-003", "SC-004", "SC-006", "SC-008", "SC-009")
    }
    assert (tmp_path / "reports" / "poc2_summary.md").exists()
    assert (tmp_path / "reports" / "poc2_summary.csv").exists()
    assert "Residual original drums" in markdown and "kick 5" in markdown


def test_low_f1_and_slow_timing(tmp_path):
    for i in range(5):
        write_eval(tmp_path, f"e{i}", f"run{i}", "td17_midi", tp=6, fp=3, fn=3, error_ms=12.0)
    s = status(summarize(tmp_path)[0])
    assert s["SC-001"] == "FAIL"
    assert s["SC-002"] == "FAIL"
    assert s["SC-003"] == "INSUFFICIENT"  # no manual annotation
    assert s["SC-009"] == "N/A"


def test_latest_evaluation_per_song_counts_once(tmp_path):
    write_eval(tmp_path, "e0", "run0", "td17_midi", tp=1, fp=9, fn=9)  # older, bad
    write_eval(tmp_path, "e1", "run0", "td17_midi")  # newer
    criteria, _ = summarize(tmp_path)
    assert "TD-17 1" in next(c.result for c in criteria if c.criterion == "SC-003")
    assert status(criteria)["SC-001"] == "PASS"


def test_calibration_and_speed(tmp_path):
    write_eval(tmp_path, "e0", "run0", "td17_midi", std=1.5, sec=200.0)
    s = status(summarize(tmp_path)[0])
    assert s["SC-008"] == "FAIL"
    assert s["SC-004"] == "FAIL"


def test_no_evaluations(tmp_path):
    (tmp_path / "evaluations").mkdir()
    with pytest.raises(UserInputError):
        summarize(tmp_path)
