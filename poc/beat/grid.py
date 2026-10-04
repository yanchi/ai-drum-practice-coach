"""Beat grid building blocks: filling skipped beats, aligning the grid to the drums,
downbeat regularization, BPM and meter (specs/003-beat-bar-mapping/research.md R-02〜R-04)."""

from __future__ import annotations

from collections import Counter

import numpy as np

from poc.domain import RunWarning

LOCAL_WINDOW = 16  # beats around a gap used for the local median interval


def fill_gaps(
    beats: list[float], max_missing: int = 3, tolerance: float = 0.15
) -> tuple[list[float], list[bool]]:
    """Like `fill_beat_gaps`, but compares each gap with the median interval of the
    surrounding LOCAL_WINDOW beats (follows tempo drift), or of the whole song when that is
    shorter (a long stretch tracked at half tempo has a doubled local median).
    Returns (times, inferred flags)."""
    if len(beats) < 3:
        return list(beats), [False] * len(beats)
    diffs = np.diff(beats)
    overall = float(np.median(diffs))
    half = LOCAL_WINDOW // 2
    times, inferred = [beats[0]], [False]
    for j in range(1, len(beats)):
        gap = beats[j] - beats[j - 1]
        local = float(np.median(diffs[max(0, j - 1 - half) : j - 1 + half]))
        median = min(local, overall)
        k = int(round(gap / median))
        if 2 <= k <= max_missing + 1 and abs(gap / k - median) < tolerance * median:
            times += [round(beats[j - 1] + gap * i / k, 4) for i in range(1, k)]
            inferred += [True] * (k - 1)
        times.append(beats[j])
        inferred.append(False)
    return times, inferred


def find_gaps(beats: list[float], factor: float = 1.5) -> list[tuple[float, float]]:
    """Spans where consecutive beats are more than `factor` median intervals apart."""
    if len(beats) < 3:
        return []
    diffs = np.diff(beats)
    median = float(np.median(diffs))
    return [(beats[i], beats[i + 1]) for i in np.flatnonzero(diffs > factor * median)]


def regularize_downbeats(
    activation: list[float | None], meter: int = 4, switch_penalty: float = 4.0
) -> tuple[list[int], list[int]]:
    """Choose the bar position (phase) of every beat with Viterbi (research R-03).

    Phase 0 is the downbeat. Moving on by one phase per beat is free; any other phase costs
    `switch_penalty`. A beat costs -log(a) as a downbeat and -log(1 - a) otherwise, where a
    is its downbeat activation (None = inferred beat, no evidence). Returns the indices of
    the downbeats and of the beats where the phase jumps."""
    n = len(activation)
    if n == 0:
        return [], []
    a = np.array([0.5 if v is None else v for v in activation], dtype=float).clip(0.01, 0.99)
    emission = np.full((n, meter), 0.0)
    emission[:, 0] = -np.log(a)
    emission[:, 1:] = -np.log(1 - a)[:, None]
    transition = np.full((meter, meter), switch_penalty)
    for p in range(meter):
        transition[p, (p + 1) % meter] = 0.0
    cost = emission[0].copy()
    back = np.zeros((n, meter), dtype=int)
    for i in range(1, n):
        total = cost[:, None] + transition  # [from, to]
        back[i] = total.argmin(axis=0)
        cost = total.min(axis=0) + emission[i]
    phases = [int(cost.argmin())]
    for i in range(n - 1, 0, -1):
        phases.append(int(back[i, phases[-1]]))
    phases.reverse()
    downbeats = [i for i, p in enumerate(phases) if p == 0]
    changes = [i for i in range(1, n) if phases[i] != (phases[i - 1] + 1) % meter]
    return downbeats, changes


def estimate_meter(beats: list[float], raw_downbeats: list[float]) -> int:
    """Most common number of beats between consecutive raw downbeats (4 if unknown)."""
    if len(raw_downbeats) < 2:
        return 4
    index = np.searchsorted(beats, np.asarray(raw_downbeats) - 1e-3)
    counts = [int(c) for c in np.diff(index) if c > 0]
    return Counter(counts).most_common(1)[0][0] if counts else 4


def choose_downbeats(
    beats: list[float],
    activation: list[float | None],
    raw_downbeats: list[float],
    meter: int,
    regularize: bool = True,
) -> dict:
    """Downbeats used for mapping: regularized when the meter is 4, raw otherwise."""
    if not regularize:
        return {
            "downbeats": list(raw_downbeats),
            "source": "raw",
            "phase_changes": [],
            "warnings": [],
        }
    if meter != 4:
        warning = RunWarning(
            code="meter_not_four",
            message=f"meter {meter} is not 4; downbeats are not regularized",
            value=float(meter),
        )
        return {
            "downbeats": list(raw_downbeats),
            "source": "raw",
            "phase_changes": [],
            "warnings": [warning],
        }
    indices, changes = regularize_downbeats(activation, meter)
    return {
        "downbeats": [beats[i] for i in indices],
        "source": "regularized",
        "phase_changes": [beats[i] for i in changes],
        "warnings": [],
    }


BPM_SPAN = 8  # beats per span when measuring the tempo


def bpm_overall(beats: list[float]) -> float:
    """BPM from the median of 8-beat spans. A single interval is quantized by the beat
    tracker's 20 ms frames (0.32 vs 0.34 s at 187 BPM); a span divides that error by 8.
    Spans across a break (any interval over 1.5 medians) are skipped."""
    if len(beats) < 2:
        return 0.0
    b = np.asarray(beats)
    diffs = np.diff(b)
    if len(b) <= BPM_SPAN:
        return round(60.0 / float(np.median(diffs)), 2)
    median = float(np.median(diffs))
    spans = [
        (b[i + BPM_SPAN] - b[i]) / BPM_SPAN
        for i in range(len(b) - BPM_SPAN)
        if diffs[i : i + BPM_SPAN].max() <= 1.5 * median
    ]
    return round(60.0 / float(np.median(spans) if spans else median), 2)


def bpm_sections(
    beats: list[float], downbeats: list[float], bars_per_section: int = 16
) -> list[dict[str, float]]:
    """BPM per run of `bars_per_section` bars."""
    if len(beats) < 2:
        return []
    starts = [beats[0]] + list(downbeats[bars_per_section::bars_per_section])
    edges = starts + [beats[-1] + 1e-6]
    sections = []
    b = np.asarray(beats)
    for start, end in zip(edges[:-1], edges[1:], strict=True):
        inside = b[(b >= start) & (b <= end)]
        if len(inside) > 1:
            sections.append(
                {
                    "start_sec": float(start),
                    "end_sec": float(min(end, beats[-1])),
                    "bpm": bpm_overall(list(inside)),
                }
            )
    return sections


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
