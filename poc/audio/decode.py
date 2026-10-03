"""Decode audio files to float32 arrays with ffmpeg (research R-04)."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import numpy as np

from poc.audio.probe import check_drm, probe
from poc.domain import RunWarning, Song
from poc.errors import InputReadError

DURATION_TOLERANCE_SEC = 0.001


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_song(path: Path) -> tuple[Song, np.ndarray, list[RunWarning]]:
    """Decode the first audio stream at its original sample rate and channel count.

    Returns the song, audio shaped (channels, samples) as float32, and warnings.
    """
    path = Path(path)
    info = probe(path)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-f",
            "f32le",
            "-acodec",
            "pcm_f32le",
            "-ac",
            str(info.channels),
            "-ar",
            str(info.sample_rate),
            "pipe:1",
        ],
        capture_output=True,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode(errors="replace")
        check_drm(path, None, stderr)
        raise InputReadError(path, stderr.strip() or "ffmpeg failed")

    audio = np.frombuffer(proc.stdout, dtype="<f4").reshape(-1, info.channels).T.copy()
    song = Song(
        path=path.resolve(),
        sha256=_sha256(path),
        format=info.format_name,
        codec=info.codec,
        sample_rate=info.sample_rate,
        channels=info.channels,
        num_samples=audio.shape[1],
    )

    warnings = []
    if info.duration_sec is not None:
        diff = abs(song.duration_sec - info.duration_sec)
        if diff > DURATION_TOLERANCE_SEC:
            warnings.append(
                RunWarning(
                    code="duration_mismatch",
                    message=(
                        f"decoded duration {song.duration_sec:.4f}s differs from container "
                        f"duration {info.duration_sec:.4f}s"
                    ),
                    value=diff,
                    threshold=DURATION_TOLERANCE_SEC,
                )
            )
    return song, audio, warnings
