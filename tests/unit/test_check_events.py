import json

import pytest

from poc.errors import UserInputError
from poc.transcription.run import compare_transcriptions

EVENTS = [
    {"time_sec": 0.5, "instrument": "kick", "strength": 0.8},
    {"time_sec": 1.0, "instrument": "snare", "strength": 0.9},
]


def make(tmp_path, name, events=EVENTS, sha="a" * 64, thresholds=(0.2,), device="cpu"):
    d = tmp_path / name
    d.mkdir()
    data = {
        "schema_version": 1,
        "input": {"audio_sha256": sha},
        "transcriber": {
            "method": "adtof-pytorch",
            "version": "0.1.0",
            "params": {"thresholds": list(thresholds)},
            "device": device,
        },
        "events": events,
    }
    (d / "transcription.json").write_text(json.dumps(data))
    return d


def test_identical(tmp_path):
    result = compare_transcriptions(make(tmp_path, "a"), make(tmp_path, "b"))
    assert result == (2, 2, 0, True)


def test_moved_event(tmp_path):
    moved = [dict(EVENTS[0], time_sec=0.51), EVENTS[1]]
    result = compare_transcriptions(make(tmp_path, "a"), make(tmp_path, "b", events=moved))
    assert result == (2, 2, 1, False)


def test_extra_event(tmp_path):
    extra = [*EVENTS, {"time_sec": 2.0, "instrument": "hihat", "strength": 0.3}]
    assert compare_transcriptions(make(tmp_path, "a"), make(tmp_path, "b", events=extra)) == (
        2,
        3,
        1,
        False,
    )


@pytest.mark.parametrize("kwargs", [{"sha": "b" * 64}, {"thresholds": (0.3,)}])
def test_different_input_or_settings(tmp_path, kwargs):
    with pytest.raises(UserInputError):
        compare_transcriptions(make(tmp_path, "a"), make(tmp_path, "b", **kwargs))
