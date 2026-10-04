"""Beat grid building blocks: filling skipped beats, aligning the grid to the drums,
downbeat regularization, BPM and meter (specs/003-beat-bar-mapping/research.md R-02〜R-04)."""

from __future__ import annotations

import numpy as np


def fill_beat_gaps(
    beats: list[float], max_missing: int = 3, tolerance: float = 0.15
) -> list[float]:
    """Insert evenly spaced beats where the tracker skipped 1 to `max_missing` beats.

    A gap is filled when it is close (within `tolerance` of the median interval per beat)
    to a whole number of median intervals. Longer gaps (e.g. a section without drums) stay."""
    if len(beats) < 3:
        return list(beats)
    median = float(np.median(np.diff(beats)))
    out = [beats[0]]
    for t in beats[1:]:
        gap = t - out[-1]
        k = int(round(gap / median))
        if 2 <= k <= max_missing + 1 and abs(gap / k - median) < tolerance * median:
            start = out[-1]
            out += [round(start + gap * j / k, 4) for j in range(1, k)]
        out.append(t)
    return out


def drum_offset_sec(beats: list[float], onsets: list[float], window: float = 0.06) -> float | None:
    """Median of (onset - nearest beat) over the onsets within `window` of a beat.

    Beat This! places beats on a 20 ms frame grid and tends to lag the drum onsets, so the
    click is shifted by this offset to sound with the original drums."""
    if len(beats) < 2 or not onsets:
        return None
    b = np.asarray(beats)
    t = np.asarray(onsets)
    i = np.clip(np.searchsorted(b, t), 1, len(b) - 1)
    nearest = np.where(np.abs(b[i] - t) < np.abs(b[i - 1] - t), b[i], b[i - 1])
    diff = t - nearest
    diff = diff[np.abs(diff) <= window]
    return round(float(np.median(diff)), 4) if len(diff) else None
