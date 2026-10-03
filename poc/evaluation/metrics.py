"""Processing time, memory and environment for run.json (research R-11)."""

from __future__ import annotations

import platform
import resource
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError, version
from time import perf_counter


class Stopwatch:
    """Measures named stages (repeated stages accumulate) and the total since creation."""

    def __init__(self) -> None:
        self._start = perf_counter()
        self._stages: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        start = perf_counter()
        try:
            yield
        finally:
            self._stages[name] = self._stages.get(name, 0.0) + perf_counter() - start

    def result(self) -> dict[str, float]:
        total = perf_counter() - self._start
        return {**{k: round(v, 3) for k, v in self._stages.items()}, "total": round(total, 3)}


def peak_rss_bytes() -> int:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024  # Linux reports KiB


def mps_driver_bytes(device: str) -> int | None:
    """Memory held by the Metal driver. Apple Silicon has unified memory, so GPU
    allocations may not show up in RSS; record both."""
    if device != "mps":
        return None
    import torch

    return int(torch.mps.driver_allocated_memory())


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not installed"


def _ffmpeg_version() -> str:
    if shutil.which("ffmpeg") is None:
        return "not found"
    proc = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    return proc.stdout.splitlines()[0] if proc.stdout else "unknown"


def _machine() -> str:
    if sys.platform == "darwin":
        proc = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    return platform.processor() or platform.machine()


def environment_info() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "torch": _package_version("torch"),
        "demucs": _package_version("demucs"),
        "ffmpeg": _ffmpeg_version(),
        "platform": platform.platform(),
        "machine": _machine(),
    }
