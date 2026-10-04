import pytest

from poc.errors import UserInputError
from poc.evaluation.annotate import write_beats
from poc.evaluation.beat_groundtruth import load_beat_annotation


def write(tmp_path, regions="beat_regions:\n  - [10.0, 20.0]\n", csv=None):
    path = tmp_path / "annotation.yaml"
    path.write_text(f"schema_version: 1\npoc1_run_id: run-a\n{regions}")
    if csv is not None:
        (tmp_path / "beats.csv").write_text(csv)
    return path


def test_load_beat_annotation(tmp_path):
    path = write(tmp_path, csv="time_sec,label\n9.5,d\n10.0,d\n10.5,b\n11.0,b\n20.5,b\n")
    gt = load_beat_annotation(path)
    assert gt.source == "manual"
    assert gt.poc1_run_id == "run-a"
    assert gt.regions == [(10.0, 20.0)]
    assert gt.beats == [10.0, 10.5, 11.0]
    assert gt.downbeats == [10.0]


@pytest.mark.parametrize(
    ("regions", "csv"),
    [("", "time_sec,label\n10,b\n"), ("beat_regions:\n  - [10.0, 20.0]\n", "10,x\n")],
)
def test_load_beat_annotation_errors(tmp_path, regions, csv):
    with pytest.raises(UserInputError):
        load_beat_annotation(write(tmp_path, regions, csv))


def test_load_beat_annotation_needs_beats_csv(tmp_path):
    with pytest.raises(UserInputError):
        load_beat_annotation(write(tmp_path))


def test_write_beats(tmp_path):
    out = tmp_path / "beats.csv"
    assert write_beats(out, "time_sec,label\n10.5,b\n10,d\n") == 2
    assert out.read_text() == "time_sec,label\n10.000,d\n10.500,b\n"
    with pytest.raises(UserInputError):
        write_beats(out, "10,k\n")
