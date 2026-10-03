"""Find the TD-17 audio device (sounddevice) and MIDI input port (python-rtmidi)."""

from __future__ import annotations

from poc.errors import UserInputError

DRIVER_HINT = (
    "Connect the TD-17 by USB, install the Roland TD-17 driver, and set "
    "SETUP > USB > USB Driver Mode = VENDOR (then restart the TD-17)."
)


def audio_devices() -> list[dict]:
    import sounddevice as sd

    return [dict(d, index=i) for i, d in enumerate(sd.query_devices())]


def midi_input_ports() -> list[str]:
    import rtmidi

    return rtmidi.MidiIn().get_ports()


def find_audio_device(name: str) -> dict:
    """A device whose name contains `name` and that can both play and record stereo."""
    for device in audio_devices():
        if (
            name.lower() in device["name"].lower()
            and device["max_input_channels"] >= 2
            and device["max_output_channels"] >= 2
        ):
            return device
    raise UserInputError(f"audio device {name!r} (stereo in/out) not found. {DRIVER_HINT}")


def find_midi_port(name: str) -> int:
    for index, port in enumerate(midi_input_ports()):
        if name.lower() in port.lower():
            return index
    raise UserInputError(f"MIDI input {name!r} not found. {DRIVER_HINT}")


def describe_devices() -> str:
    lines = ["Audio devices:"]
    for d in audio_devices():
        lines.append(
            f"  [{d['index']}] {d['name']}  in={d['max_input_channels']} "
            f"out={d['max_output_channels']} sr={d['default_samplerate']:g}"
        )
    lines.append("MIDI inputs:")
    lines.extend(f"  [{i}] {p}" for i, p in enumerate(midi_input_ports()))
    return "\n".join(lines)
