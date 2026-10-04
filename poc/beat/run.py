"""`poc beats`: BeatGrid of a PoC 1 run (specs/003-beat-bar-mapping, US1 / US4)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf

from poc.audio.decode import load_song
from poc.beat.base import BeatEstimator
from poc.beat.beats import latest_drum_stem_onsets
from poc.beat.grid import (
    bpm_overall,
    bpm_sections,
    choose_downbeats,
    drum_offset_sec,
    estimate_meter,
    fill_gaps,
    find_gaps,
)
from poc.domain import Beat, BeatGrid
from poc.errors import PocError, UserInputError
from poc.evaluation.metrics import Stopwatch, environment_info, peak_rss_bytes
from poc.recording.record import add_beat_clicks
from poc.transcription.run import _sha256, load_poc1_run, resolve_input

BeatInput = Literal["mix", "drum_stem"]
CHECK_GAIN = 0.5  # the song under the clicks (-6 dB)


def run_beats(
    poc1_run_dir: Path,
    input_kind: BeatInput,
    output_dir: Path,
    estimator: BeatEstimator,
    *,
    regularize: bool = True,
    offset: bool = False,  # aligning to the drums is opt-in (PoC 3 Human Review)
    transcriptions_dir: Path = Path("output/transcriptions"),
    now: datetime | None = None,
) -> Path:
    """Estimate, fill, regularize and align the beats of one input. Returns the output dir."""
    poc1_run_dir = Path(poc1_run_dir)
    output_dir = Path(output_dir)
    run = load_poc1_run(poc1_run_dir)
    audio_path = resolve_input(poc1_run_dir, input_kind)
    watch = Stopwatch()

    # Look up the alignment source first so a missing transcription fails before the model runs.
    offset_from, onsets = (None, [])
    if offset:
        offset_from, onsets = latest_drum_stem_onsets(run["run_id"], transcriptions_dir)

    with watch.stage("load"):
        song, song_audio, _ = load_song(Path(run["song"]["path"]))
        if input_kind == "mix":
            audio, sr = song_audio, song.sample_rate
        else:
            data, sr = sf.read(audio_path, dtype="float32", always_2d=True)
            audio = data.T
        audio_sha = _sha256(audio_path)

    with watch.stage("estimate"):
        estimate = estimator.estimate(audio.mean(axis=0), sr)

    with watch.stage("grid"):
        times, inferred = fill_gaps(estimate.beats)
        by_time = dict(zip(estimate.beats, estimate.downbeat_activation, strict=True))
        activation = [
            None if flag else by_time.get(t) for t, flag in zip(times, inferred, strict=True)
        ]
        meter = estimate_meter(times, estimate.downbeats)
        chosen = choose_downbeats(times, activation, estimate.downbeats, meter, regularize)
        shift = (drum_offset_sec(times, onsets) or 0.0) if offset else 0.0

        def moved(values: list[float]) -> list[float]:
            return [round(t + shift, 4) for t in values]

        beats = [
            Beat(time_sec=t, inferred=flag, downbeat_activation=a)
            for t, flag, a in zip(moved(times), inferred, activation, strict=True)
        ]
        downbeats = moved(chosen["downbeats"])
        raw = moved(estimate.downbeats)
        changed = len(set(downbeats) ^ set(raw)) // 2 if chosen["source"] == "regularized" else 0

    now = now or datetime.now().astimezone()
    beatgrid_id = f"{now:%Y%m%d-%H%M%S}_{input_kind}_{audio_sha[:8]}"
    final_dir = output_dir / beatgrid_id
    partial_dir = output_dir / f"{beatgrid_id}.partial"
    if final_dir.exists() or partial_dir.exists():
        raise PocError(f"beat grid directory already exists: {final_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    partial_dir.mkdir()
    try:
        with watch.stage("write"):
            check = (song_audio * CHECK_GAIN).astype(np.float32)
            add_beat_clicks(check, 0, [b.time_sec for b in beats], downbeats, song.sample_rate)
            sf.write(partial_dir / "check.wav", check.T, song.sample_rate, subtype="FLOAT")
        times_shifted = [b.time_sec for b in beats]
        grid = BeatGrid(
            beatgrid_id=beatgrid_id,
            created_at=now.isoformat(timespec="seconds"),
            input={
                "kind": input_kind,
                "poc1_run_id": run["run_id"],
                "audio_sha256": audio_sha,
                "duration_sec": song.duration_sec,
            },
            estimator=estimate.info,
            beats=beats,
            downbeats=downbeats,
            downbeats_raw=raw,
            downbeat_source=chosen["source"],
            meter=meter,
            bpm=bpm_overall(times_shifted),
            bpm_sections=bpm_sections(times_shifted, downbeats),
            offset={"applied_ms": round(shift * 1000, 1), "from_transcription_id": offset_from},
            regularization={
                "applied": chosen["source"] == "regularized",
                "phase_changes": moved(chosen["phase_changes"]),
                "changed_downbeats": changed,
            },
            gaps=find_gaps(times_shifted),
            warnings=chosen["warnings"],
            timings_sec=watch.result(),
            peak_memory={"rss_bytes": peak_rss_bytes()},
            environment=environment_info(),
        )
        (partial_dir / "beatgrid.json").write_text(
            json.dumps(grid.to_dict(), indent=2, ensure_ascii=False) + "\n"
        )
        partial_dir.rename(final_dir)
    except BaseException:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise
    return final_dir


def load_beatgrid(beatgrid_dir: Path) -> BeatGrid:
    path = Path(beatgrid_dir) / "beatgrid.json"
    if not path.exists():
        raise UserInputError(f"not a beat grid directory (beatgrid.json not found): {beatgrid_dir}")
    return BeatGrid.from_dict(json.loads(path.read_text()))
