import pytest

from poc.errors import UserInputError
from poc.transcription.adtof_adapter import AdtofTranscriber, parse_thresholds


def test_parse_thresholds():
    assert parse_thresholds("kick=0.12, hihat=0.1") == {"kick": 0.12, "hihat": 0.1}
    assert parse_thresholds("") == {}


@pytest.mark.parametrize(
    "text", ["cowbell=0.1", "kick=0", "kick=1.5", "kick=abc", "kick", "kick=0.1,kick=0.2"]
)
def test_parse_thresholds_errors(text):
    with pytest.raises(UserInputError):
        parse_thresholds(text)


def test_override_keeps_other_defaults():
    default = AdtofTranscriber().thresholds
    tuned = AdtofTranscriber(thresholds={"kick": 0.12, "hihat": 0.12}).thresholds
    assert tuned["kick"] == 0.12
    assert tuned["hihat"] == 0.12
    assert tuned["snare"] == default["snare"]
    assert tuned["tom"] == default["tom"]
    assert tuned["cymbal"] == default["cymbal"]
    assert default == {"kick": 0.22, "snare": 0.24, "tom": 0.32, "hihat": 0.22, "cymbal": 0.30}
