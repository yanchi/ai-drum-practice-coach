import csv
import json

import pytest
import yaml

from poc.errors import UserInputError
from poc.evaluation.sheet import render_template
from poc.evaluation.summary import summarize


def make_run(
    runs_dir,
    run_id,
    *,
    sha="a" * 64,
    verdict="ok",
    issues=(),
    lag_ms=0.0,
    timings=True,
):
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    run = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "succeeded",
        "song": {"sha256": sha, "duration_sec": 120.0, "sample_rate": 44100},
        "separator": {"method": "demucs", "version": "4.1.0", "params": {}, "device": "mps"},
        "stems": [{"kind": "drums", "path": "drums.wav"}],
        "alignment": {"lag_ms": lag_ms, "passed": abs(lag_ms) <= 1.0},
        "timings_sec": {"total": 60.0} if timings else None,
        "peak_memory": {"rss_bytes": 2 * 1024**3, "mps_driver_bytes": None} if timings else None,
        "environment": {"python": "3.11"} if timings else None,
        "warnings": [],
    }
    (run_dir / "run.json").write_text(json.dumps(run))
    sheet = yaml.safe_load(render_template(run_id, song_label=run_id))
    sheet.update(verdict=verdict, issues=list(issues), genre="rock")
    (run_dir / "evaluation.yaml").write_text(yaml.safe_dump(sheet, allow_unicode=True))
    return run_dir


def statuses(result):
    return {c.criterion: c.status for c in result.criteria}


def five_songs(runs_dir, **kwargs):
    for i in range(5):
        make_run(runs_dir, f"run{i}", sha=str(i) * 64, **kwargs)


def test_all_pass(tmp_path):
    runs = tmp_path / "runs"
    five_songs(runs)
    result = summarize(runs, tmp_path / "reports")
    assert set(statuses(result).values()) == {"PASS"}
    assert (tmp_path / "reports" / "summary.md").exists()
    rows = list(csv.DictReader((tmp_path / "reports" / "summary.csv").open()))
    assert len(rows) == 5
    assert rows[0]["verdict"] == "ok"
    assert float(rows[0]["peak_rss_mb"]) == pytest.approx(2048.0)


def test_insufficient_songs(tmp_path):
    runs = tmp_path / "runs"
    make_run(runs, "run0")
    s = statuses(summarize(runs, tmp_path / "reports"))
    assert s["SC-001"] == s["SC-002"] == "INSUFFICIENT"


def test_repeated_song_counts_once(tmp_path):
    runs = tmp_path / "runs"
    for i in range(5):
        make_run(runs, f"run{i}", sha="a" * 64)
    assert statuses(summarize(runs, tmp_path / "reports"))["SC-001"] == "INSUFFICIENT"


def test_any_ng_fails_even_with_few_songs(tmp_path):
    runs = tmp_path / "runs"
    make_run(runs, "good")
    make_run(runs, "bad", sha="b" * 64, verdict="ng", issues=["hihat"])
    result = summarize(runs, tmp_path / "reports")
    sc002 = next(c for c in result.criteria if c.criterion == "SC-002")
    assert sc002.status == "FAIL"
    assert "NG: bad" in sc002.result
    assert "hihat 1" in result.markdown


def test_alignment_fail(tmp_path):
    runs = tmp_path / "runs"
    five_songs(runs, lag_ms=2.0)
    assert statuses(summarize(runs, tmp_path / "reports"))["SC-004"] == "FAIL"


def test_missing_timings(tmp_path):
    runs = tmp_path / "runs"
    five_songs(runs, timings=False)
    s = statuses(summarize(runs, tmp_path / "reports"))
    assert s["SC-005"] == "N/A"
    assert s["SC-007"] == "FAIL"


def test_sc005_normalizes_to_four_minutes(tmp_path):
    runs = tmp_path / "runs"
    five_songs(runs)  # 60 s for a 120 s song -> 120 s for 240 s
    result = summarize(runs, tmp_path / "reports")
    sc005 = next(c for c in result.criteria if c.criterion == "SC-005")
    assert "2.0 min" in sc005.result


def test_incomplete_sheets_are_skipped(tmp_path):
    runs = tmp_path / "runs"
    make_run(runs, "done")
    make_run(runs, "todo", verdict=None)
    result = summarize(runs, tmp_path / "reports")
    assert [r.run_id for r in result.rows] == ["done"]
    assert result.incomplete == ["todo"]


def test_no_completed_sheets(tmp_path):
    runs = tmp_path / "runs"
    make_run(runs, "todo", verdict=None)
    with pytest.raises(UserInputError, match="todo"):
        summarize(runs, tmp_path / "reports")
