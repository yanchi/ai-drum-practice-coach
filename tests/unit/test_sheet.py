import pytest
import yaml

from poc.errors import UserInputError
from poc.evaluation.sheet import SheetValidationError, load_sheet, render_template


def filled(run_id="20261004-001919_3e21c73e"):
    data = yaml.safe_load(render_template(run_id))
    data.update(song_label="B・BLUE", genre="rock", evaluated_at="2026-10-04")
    data["listening"] = {"drum_clarity": 4, "bleed": 3, "artifacts": 4}
    for i, section in enumerate(data["sections"]):
        section["start_sec"] = 10.0 * i
        section["end_sec"] = 10.0 * i + 8
        section["counts"] = {
            "kick": {"original": 8, "detected": 8},
            "snare": {"original": 4, "detected": 4},
            "hihat": {"original": 16, "detected": 14},
        }
    return data


def write(tmp_path, data):
    path = tmp_path / "evaluation.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    return path


def test_template_matches_contract():
    text = render_template("RUN")
    assert text.startswith("# 評価シート (PoC 1)")
    data = yaml.safe_load(text)
    assert data["schema_version"] == 1
    assert data["run_id"] == "RUN"
    assert [s["label"] for s in data["sections"]] == ["verse", "chorus", "fill"]
    assert data["listening"] == {"drum_clarity": None, "bleed": None, "artifacts": None}
    assert data["sections"][0]["counts"]["kick"] == {"original": None, "detected": None}


def test_template_is_incomplete(tmp_path):
    path = tmp_path / "evaluation.yaml"
    path.write_text(render_template("RUN"))
    assert load_sheet(path) is None


def test_filled_sheet_loads(tmp_path):
    sheet = load_sheet(write(tmp_path, filled()))
    assert sheet.song_label == "B・BLUE"
    assert sheet.evaluated_at == "2026-10-04"
    assert sheet.listening.drum_clarity == 4
    assert sheet.sections[2].counts["hihat"].detected == 14


def test_one_null_makes_sheet_incomplete(tmp_path):
    data = filled()
    data["sections"][1]["counts"]["snare"]["detected"] = None
    assert load_sheet(write(tmp_path, data)) is None


def test_empty_label_makes_sheet_incomplete(tmp_path):
    data = filled()
    data["song_label"] = ""
    assert load_sheet(write(tmp_path, data)) is None


def mutate_rating(d):
    d["listening"]["drum_clarity"] = 6


def mutate_detected(d):
    d["sections"][0]["counts"]["kick"]["detected"] = 9


def mutate_negative(d):
    d["sections"][0]["counts"]["kick"]["original"] = -1


def mutate_end(d):
    d["sections"][0]["end_sec"] = d["sections"][0]["start_sec"]


def mutate_two_sections(d):
    d["sections"] = d["sections"][:2]


def mutate_duplicate_label(d):
    d["sections"][1]["label"] = "verse"


def mutate_schema(d):
    d["schema_version"] = 99


@pytest.mark.parametrize(
    ("mutate", "field"),
    [
        (mutate_rating, "listening.drum_clarity"),
        (mutate_detected, "sections[0].counts.kick"),
        (mutate_negative, "sections[0].counts.kick"),
        (mutate_end, "sections[0].end_sec"),
        (mutate_two_sections, "sections"),
        (mutate_duplicate_label, "sections"),
        (mutate_schema, "schema_version"),
    ],
)
def test_validation_errors(tmp_path, mutate, field):
    data = filled()
    mutate(data)
    path = write(tmp_path, data)
    with pytest.raises(SheetValidationError) as exc:
        load_sheet(path)
    assert isinstance(exc.value, UserInputError)
    assert str(path) in str(exc.value)
    assert field in str(exc.value)
