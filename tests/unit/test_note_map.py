import pytest

from poc.errors import UserInputError
from poc.recording.note_map import load_note_map, parse_note_on


@pytest.fixture
def note_map():
    return load_note_map()


@pytest.mark.parametrize(
    ("note", "instrument"),
    [
        (36, "kick"),
        (38, "snare"),
        (40, "snare"),
        (37, "snare"),
        (42, "hihat"),
        (22, "hihat"),
        (46, "hihat"),
        (26, "hihat"),
        (44, "hihat"),  # pedal "chick" counts as a hihat hit
    ],
)
def test_evaluated_pads(note_map, note, instrument):
    assert note_map.instrument_for(note) == instrument
    assert note_map.is_known(note)


@pytest.mark.parametrize("note", [48, 50, 45, 47, 43, 58, 49, 55, 57, 52, 51, 59, 53])
def test_toms_and_cymbals_are_ignored(note_map, note):
    assert note_map.instrument_for(note) is None
    assert note_map.is_known(note)


def test_unknown_note(note_map):
    assert note_map.instrument_for(100) is None
    assert not note_map.is_known(100)


def test_to_dict_round_trip(note_map):
    data = note_map.to_dict()
    assert data["kick"] == [36]
    assert 44 in data["hihat"]


def test_invalid_map(tmp_path):
    path = tmp_path / "map.yaml"
    path.write_text("kick: [36]\nsnare: [36]\n")  # the same note twice
    with pytest.raises(UserInputError):
        load_note_map(path)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ([0x99, 36, 100], (36, 100)),  # note on, channel 10
        ([0x90, 38, 64], (38, 64)),  # note on, channel 1
        ([0x99, 36, 0], None),  # velocity 0 = note off
        ([0x89, 36, 64], None),  # note off
        ([0xB9, 4, 90], None),  # CC #4 (hihat pedal position)
        ([0xA9, 46, 10], None),  # aftertouch (cymbal choke)
        ([], None),
    ],
)
def test_parse_note_on(message, expected):
    assert parse_note_on(message) == expected


def test_drop_double_triggers(note_map):
    from poc.recording.note_map import drop_double_triggers

    notes = [
        {"time_sec": 1.000, "note": 36, "velocity": 60},
        {"time_sec": 1.038, "note": 36, "velocity": 26},  # beater bounce: dropped
        {"time_sec": 1.010, "note": 42, "velocity": 50},  # another instrument: kept
        {"time_sec": 1.100, "note": 36, "velocity": 40},  # 100 ms later: a real hit
        {"time_sec": 2.000, "note": 38, "velocity": 50},
        {"time_sec": 2.020, "note": 40, "velocity": 30},  # snare head then rim: same instrument
        {"time_sec": 2.010, "note": 48, "velocity": 50},  # tom: not evaluated, kept
    ]
    kept, dropped = drop_double_triggers(notes, note_map)
    assert dropped == 2
    assert [(n["time_sec"], n["note"]) for n in kept] == [
        (1.0, 36),
        (1.01, 42),
        (1.1, 36),
        (2.0, 38),
        (2.01, 48),
    ]
