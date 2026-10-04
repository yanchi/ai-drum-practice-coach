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


DOUBLE_TRIGGER_SEC = 0.04  # a second note this close is always a double trigger
BOUNCE_SEC = 0.08  # ... and up to this close if it is much weaker (beater bounce)
BOUNCE_MAX_VELOCITY_RATIO = 0.6


def drop_double_triggers(notes: list[dict], note_map: NoteMap) -> tuple[list[dict], int]:
    """Drop extra notes that the TD-17 sends for a single hit of an evaluated instrument.

    A note is dropped when, for the same instrument, it comes within DOUBLE_TRIGGER_SEC of
    the previous note (kept or dropped, so retrigger chains go together), or within
    BOUNCE_SEC of the last kept note with at most BOUNCE_MAX_VELOCITY_RATIO of its velocity.
    Measured on the developer's TD-17: the kick beater bounce arrives 30-70 ms after the hit
    at 0.27-0.49 of its velocity, and the snare head retriggers 20-50 ms apart, while only
    one hit sounds (research R-06). Returns (kept notes in time order, dropped count)."""
    kept: list[dict] = []
    last_kept: dict[str, dict] = {}
    last_any: dict[str, float] = {}
    dropped = 0
    for note in sorted(notes, key=lambda n: n["time_sec"]):
        instrument = note_map.instrument_for(note["note"])
        if instrument is not None:
            previous_time = last_any.get(instrument)
            hit = last_kept.get(instrument)
            last_any[instrument] = note["time_sec"]
            retrigger = (
                previous_time is not None and note["time_sec"] - previous_time < DOUBLE_TRIGGER_SEC
            )
            bounce = (
                hit is not None
                and note["time_sec"] - hit["time_sec"] < BOUNCE_SEC
                and note["velocity"] <= BOUNCE_MAX_VELOCITY_RATIO * hit["velocity"]
            )
            if retrigger or bounce:
                dropped += 1
                continue
            last_kept[instrument] = note
        kept.append(note)
    return kept, dropped
