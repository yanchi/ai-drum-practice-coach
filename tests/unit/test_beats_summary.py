import json

from poc.evaluation.beats_summary import summarize_beats


def evaluation(
    tmp,
    eid,
    run,
    kind="mix",
    f=0.97,
    df=0.93,
    bpm=0.5,
    meter=True,
    acc=0.96,
    jitter=None,
    source="td17_taps",
):
    metrics = lambda value: {  # noqa: E731
        "tp": round(value * 100),
        "fp": 100 - round(value * 100),
        "fn": 100 - round(value * 100),
        "precision": value,
        "recall": value,
        "f_measure": value,
        "timing_ms": {"median_abs": 10.0, "p95_abs": 30.0, "median_signed": -2.0},
    }
    data = {
        "evaluation_id": eid,
        "poc1_run_id": run,
        "beatgrid": {
            "beatgrid_id": f"x_{kind}_y",
            "input_kind": kind,
            "timings_sec": {"total": 8.0},
            "duration_sec": 240.0,
            "complete": True,
        },
        "groundtruth": {"source": source},
        "variants": [
            {
                "name": name,
                "beats": metrics(f),
                "downbeats": metrics(df),
                "bpm_error_pct": bpm,
                "meter_match": meter,
                "mapping": {
                    "events": 100,
                    "matched_bar": 97,
                    "matched_beat": 97,
                    "matched_grid": round(acc * 100),
                    "accuracy": acc,
                },
            }
            for name in ("raw", "regularized", "regularized_offset")
        ],
        "tap_jitter_ms": jitter,
    }
    d = tmp / eid
    d.mkdir(parents=True)
    (d / "evaluation.json").write_text(json.dumps(data))


def test_summary_passes_with_five_songs_and_jitter(tmp_path):
    evals = tmp_path / "evals"
    for i in range(5):
        evaluation(evals, f"2026100{i}-000000_e", f"run-{i}")
    evaluation(
        evals,
        "20261009-000000_e",
        "run-0",
        jitter={"median_abs": 12.0, "p95_abs": 25.0, "count": 30},
    )
    evaluation(evals, "20261009-000001_e", "run-0", kind="drum_stem", f=0.9)
    evaluation(evals, "20261009-000002_e", "run-0", source="manual", acc=0.97)
    evaluation(evals, "20261009-000003_e", "run-1", source="manual", acc=0.96)
    md = summarize_beats(evals, tmp_path / "reports")
    assert "| SC-001" in md and "PASS" in md.split("| SC-001")[1].split("\n")[0]
    assert "PASS" in md.split("| SC-005")[1].split("\n")[0]
    assert "mix vs drum stem" in md.lower()
    assert (tmp_path / "reports" / "poc3_summary.md").exists()
    assert (tmp_path / "reports" / "poc3_summary.csv").exists()


def test_summary_is_insufficient_without_enough_songs(tmp_path):
    evals = tmp_path / "evals"
    evaluation(evals, "20261001-000000_e", "run-0", df=0.5)
    md = summarize_beats(evals, tmp_path / "reports")
    assert "INSUFFICIENT" in md.split("| SC-005")[1].split("\n")[0]
    assert "FAIL" in md.split("| SC-002")[1].split("\n")[0]


def test_mapping_accuracy_comes_from_hand_marked_beats(tmp_path):
    evals = tmp_path / "evals"
    for i in range(5):
        evaluation(evals, f"2026100{i}-000000_e", f"run-{i}", acc=0.87)  # taps: coarse
    md = summarize_beats(evals, tmp_path / "reports")
    assert "N/A" in md.split("| SC-004")[1].split("\n")[0]
    evaluation(evals, "20261009-000000_e", "run-0", source="manual", acc=0.97)
    md = summarize_beats(evals, tmp_path / "reports")
    row = md.split("| SC-004")[1].split("\n")[0]
    assert "0.970" in row and "PASS" in row and "taps: 0.870" in row
