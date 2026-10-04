import json

import pytest

from poc.errors import UserInputError
from poc.evaluation.groundtruth import load_annotation

RUN_ID = "20261004-004951_3e21c73e"


@pytest.fixture
def runs_dir(tmp_path):
    run = tmp_path / "runs" / RUN_ID
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"run_id": RUN_ID}))
    return tmp_path / "runs"


def write(tmp_path, csv_text, regions="[[10.0, 18.0], [40.0, 48.0]]", run_id=RUN_ID):
    d = tmp_path / "annotation"
    d.mkdir(exist_ok=True)
    (d / "hits.csv").write_text(csv_text)
    (d / "annotation.yaml").write_text(
        f"schema_version: 1\npoc1_run_id: {run_id}\nregions: {regions}\nhits_csv: hits.csv\n"
    )
    return d / "annotation.yaml"


def test_load(tmp_path, runs_dir):
    path = write(tmp_path, "10.5,k\n10.5,h\n11.0,s\n11.25,sg\n41.0,hg\n30.0,k\n")
    gt = load_annotation(path, runs_dir)
    assert gt.source == "manual"
    assert gt.target_kind == "poc1_song"
    assert gt.target_id == RUN_ID
    assert gt.regions == [(10.0, 18.0), (40.0, 48.0)]
    assert [(h.time_sec, h.instrument, h.ghost) for h in gt.hits] == [
        (10.5, "kick", False),
        (10.5, "hihat", False),
        (11.0, "snare", False),
        (11.25, "snare", True),
        (41.0, "hihat", False),  # "hg": hi-hat strokes are always scored
    ]  # 30.0 is outside the regions
    assert all(h.velocity is None for h in gt.hits)


def test_header_and_spaces_are_accepted(tmp_path, runs_dir):
    path = write(tmp_path, "time,label\n 10.5 , K \n")
    assert load_annotation(path, runs_dir).hits[0].instrument == "kick"


@pytest.mark.parametrize(
    ("csv_text", "regions", "run_id", "message"),
    [
        ("10.5,x\n", "[[10.0, 18.0]]", RUN_ID, "line 1"),
        ("abc,k\n", "[[10.0, 18.0]]", RUN_ID, "line 1"),
        ("10.5,k\n", "[[10.0, 18.0], [17.0, 20.0]]", RUN_ID, "overlap"),
        ("10.5,k\n", "[[18.0, 10.0]]", RUN_ID, "region"),
        ("10.5,k\n", "[[10.0, 18.0]]", "missing_run", "missing_run"),
    ],
)
def test_errors(tmp_path, runs_dir, csv_text, regions, run_id, message):
    path = write(tmp_path, csv_text, regions, run_id)
    with pytest.raises(UserInputError, match=message):
        load_annotation(path, runs_dir)
