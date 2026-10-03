"""Exceptions raised by the PoC pipeline.

`exit_code` is used by the CLI: 2 for problems caused by the user's input, 1 otherwise.
"""


class PocError(Exception):
    exit_code = 1


class UserInputError(PocError):
    exit_code = 2


class InputReadError(UserInputError):
    def __init__(self, path, reason: str):
        super().__init__(f"cannot read {path}: {reason}")


class DrmProtectedError(UserInputError):
    def __init__(self, path):
        super().__init__(
            f"{path} is DRM-protected and is not supported. "
            "Use a CD rip, DRM-free purchase, or your own recording."
        )


class UnsupportedAudioError(UserInputError):
    def __init__(self, codec: str, channels: int):
        super().__init__(
            f"unsupported audio ({codec}, {channels}ch). "
            "Supported: WAV / AIFF / MP3 / AAC / ALAC, mono or stereo."
        )


class FfmpegNotFoundError(PocError):
    def __init__(self):
        super().__init__("ffmpeg not found. Install with: brew install ffmpeg")


class SeparationError(PocError):
    def __init__(self, reason: str):
        super().__init__(f"separation failed: {reason}")
