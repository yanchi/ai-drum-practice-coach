import pytest
import yaml

from poc.errors import UserInputError
from poc.evaluation.sheet import SheetValidationError, load_sheet, render_template


def filled(**overrides):
    data = yaml.safe_load(render_template("RUN", song_label="1-10 B・BLUE"))
    data.update(verdict="ok", issues=["hihat"])
    data.update(overrides)
    return data


def write(tmp_path, data):
    path = tmp_path / "evaluation.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    return path


def test_template_prefills_song_label():
    text = render_template("RUN", song_label='1-10 B・BLUE "live"')
    assert text.startswith("# 評価シート (PoC 1)")
    data = yaml.safe_load(text)
    assert data == {
        "schema_version": 2,
        "run_id": "RUN",
        "song_label": '1-10 B・BLUE "live"',
        "genre": "",
        "evaluated_at": "",
        "verdict": None,
        "issues": [],
        "notes": "",
    }


def test_template_is_incomplete(tmp_path):
    path = tmp_path / "evaluation.yaml"
    path.write_text(render_template("RUN", song_label="song"))
    assert load_sheet(path) is None


def test_verdict_only_is_enough(tmp_path):
    sheet = load_sheet(write(tmp_path, filled(issues=[])))
    assert sheet.verdict == "ok"
    assert sheet.issues == []
    assert sheet.song_label == "1-10 B・BLUE"
    assert sheet.genre == ""


def test_verdict_is_case_insensitive_and_issues_deduplicated(tmp_path):
    sheet = load_sheet(write(tmp_path, filled(verdict="NG", issues=["hihat", "bleed", "hihat"])))
    assert sheet.verdict == "ng"
    assert sheet.issues == ["hihat", "bleed"]


def test_empty_song_label_is_incomplete(tmp_path):
    assert load_sheet(write(tmp_path, filled(song_label=""))) is None


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"verdict": "maybe"}, "verdict"),
        ({"verdict": True}, "verdict"),  # `yes` in YAML
        ({"issues": ["cowbell"]}, "issues"),
        ({"issues": "hihat"}, "issues"),
        ({"schema_version": 1}, "schema_version"),
    ],
)
def test_validation_errors(tmp_path, overrides, field):
    path = write(tmp_path, filled(**overrides))
    with pytest.raises(SheetValidationError) as exc:
        load_sheet(path)
    assert isinstance(exc.value, UserInputError)
    assert str(path) in str(exc.value)
    assert field in str(exc.value)
