"""TD-17 MIDI note numbers → evaluated instruments. Note numbers stay inside poc/recording/."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from poc.domain import EVALUATED_INSTRUMENTS
from poc.errors import UserInputError

DEFAULT_NOTE_MAP = Path(__file__).with_name("td17_note_map.yaml")
_GROUPS = (*EVALUATED_INSTRUMENTS, "ignore")


@dataclass(frozen=True)
class NoteMap:
    notes: dict[int, str | None]  # None = known pad that is not evaluated (tom / cymbal)

    def instrument_for(self, note: int) -> str | None:
        return self.notes.get(note)

    def is_known(self, note: int) -> bool:
        return note in self.notes

    def to_dict(self) -> dict[str, list[int]]:
        groups: dict[str, list[int]] = {name: [] for name in _GROUPS}
        for note, instrument in self.notes.items():
            groups[instrument or "ignore"].append(note)
        return groups


def load_note_map(path: Path | None = None) -> NoteMap:
    path = Path(path or DEFAULT_NOTE_MAP)
    data = yaml.safe_load(path.read_text()) or {}
    notes: dict[int, str | None] = {}
    for group, values in data.items():
        if group not in _GROUPS:
            raise UserInputError(f"{path}: unknown group {group!r}; use {', '.join(_GROUPS)}")
        for note in values or []:
            if not isinstance(note, int) or not 0 <= note <= 127:
                raise UserInputError(f"{path}: {group}: invalid MIDI note {note!r}")
            if note in notes:
                raise UserInputError(f"{path}: MIDI note {note} is listed twice")
            notes[note] = None if group == "ignore" else group
    return NoteMap(notes)


def parse_note_on(message: list[int]) -> tuple[int, int] | None:
    """Return (note, velocity) for a Note On with velocity > 0, else None.

    Note Off, velocity-0 Note On, control changes (e.g. hihat pedal position CC #4)
    and aftertouch are ignored.
    """
    if len(message) < 3 or message[0] & 0xF0 != 0x90 or message[2] == 0:
        return None
    return message[1], message[2]


DOUBLE_TRIGGER_SEC = 0.04


def drop_double_triggers(
    notes: list[dict], note_map: NoteMap, window_sec: float = DOUBLE_TRIGGER_SEC
) -> tuple[list[dict], int]:
    """Drop a note that follows a note of the same evaluated instrument within `window_sec`.

    The TD-17 kick pad sends a second, weaker note when the beater bounces (about 35-40 ms
    later) while only one hit sounds. Returns (kept notes in time order, dropped count)."""
    kept: list[dict] = []
    last: dict[str, float] = {}
    dropped = 0
    for note in sorted(notes, key=lambda n: n["time_sec"]):
        instrument = note_map.instrument_for(note["note"])
        if instrument is not None:
            previous = last.get(instrument)
            if previous is not None and note["time_sec"] - previous < window_sec:
                dropped += 1
                continue
            last[instrument] = note["time_sec"]
        kept.append(note)
    return kept, dropped
