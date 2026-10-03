"""Inspect audio files with ffprobe: DRM detection and format checks (research R-05)."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poc.errors import (
    DrmProtectedError,
    FfmpegNotFoundError,
    InputReadError,
    UnsupportedAudioError,
)

SUPPORTED_CODECS = {"mp3", "aac", "alac"}  # plus any "pcm_*" (WAV / AIFF)
DRM_WORDS = ("drm", "encrypted", "protected")


@dataclass(frozen=True)
class ProbeResult:
    format_name: str
    codec: str
    codec_tag: str
    sample_rate: int
    channels: int
    duration_sec: float | None


def _audio_streams(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]


def run_ffprobe(path: Path) -> tuple[dict[str, Any] | None, str]:
    """Return (parsed JSON or None on failure, stderr)."""
    if not path.is_file():
        raise InputReadError(path, "file not found")
    if shutil.which("ffprobe") is None:
        raise FfmpegNotFoundError()
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    data = json.loads(proc.stdout) if proc.returncode == 0 and proc.stdout.strip() else None
    return data, proc.stderr


def check_drm(path: Path, data: dict[str, Any] | None, stderr: str) -> None:
    """Raise DrmProtectedError if the file looks DRM-protected. Never tries to decrypt."""
    if path.suffix.lower() == ".m4p":
        raise DrmProtectedError(path)
    if data is not None:
        for stream in _audio_streams(data):
            if stream.get("codec_tag_string", "").lower() == "drms":
                raise DrmProtectedError(path)
    lowered = stderr.lower()
    if any(word in lowered for word in DRM_WORDS):
        raise DrmProtectedError(path)


def parse_probe(data: dict[str, Any]) -> ProbeResult:
    streams = _audio_streams(data)
    if not streams:
        raise UnsupportedAudioError("no audio stream", 0)
    stream = streams[0]
    codec = stream.get("codec_name", "unknown")
    channels = int(stream.get("channels", 0))
    if not (codec in SUPPORTED_CODECS or codec.startswith("pcm_")) or channels not in (1, 2):
        raise UnsupportedAudioError(codec, channels)
    duration = data.get("format", {}).get("duration")
    return ProbeResult(
        format_name=data.get("format", {}).get("format_name", "unknown"),
        codec=codec,
        codec_tag=stream.get("codec_tag_string", ""),
        sample_rate=int(stream["sample_rate"]),
        channels=channels,
        duration_sec=float(duration) if duration is not None else None,
    )


def probe(path: Path) -> ProbeResult:
    data, stderr = run_ffprobe(path)
    check_drm(path, data, stderr)
    if data is None:
        raise InputReadError(path, stderr.strip() or "ffprobe failed")
    return parse_probe(data)
