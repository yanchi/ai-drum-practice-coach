"""`poc separate`: decode, separate, check, and save one run atomically."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

from poc.audio.decode import load_song
from poc.audio.signal import estimate_lag, peak, rms_db_relative
from poc.domain import AlignmentCheck, RunWarning, SeparationRun, Song, Stem, StemKind
from poc.errors import PocError
from poc.evaluation.sheet import render_template
from poc.separation.base import SeparationOutput, Separator

NEARLY_SILENT_DB = -30.0  # research R-10
CLIP_PEAK = 1.0  # research R-08
MAX_LAG_MS = 1.0  # SC-004


def make_run_id(now: datetime, sha256: str) -> str:
    return f"{now:%Y%m%d-%H%M%S}_{sha256[:8]}"


def check_alignment(song: Song, mix: np.ndarray, out: SeparationOutput) -> AlignmentCheck:
    stems = [out.drums, out.accompaniment]
    lag, window_start = estimate_lag(mix, out.drums + out.accompaniment, song.sample_rate)
    lag_ms = lag / song.sample_rate * 1000
    length_match = all(s.shape[1] == song.num_samples for s in stems)
    return AlignmentCheck(
        method="stem_sum_xcorr",
        window_start_sec=window_start,
        lag_samples=lag,
        lag_ms=lag_ms,
        length_match=length_match,
        passed=abs(lag_ms) <= MAX_LAG_MS and length_match,
    )


def _stem(kind: StemKind, audio: np.ndarray, mix: np.ndarray, song: Song) -> Stem:
    return Stem(
        kind=kind,
        path=Path(f"{kind}.wav"),
        sample_rate=song.sample_rate,
        channels=audio.shape[0],
        num_samples=audio.shape[1],
        peak=peak(audio),
        rms_db_relative_to_mix=rms_db_relative(audio, mix),
    )


def _stem_warnings(stems: list[Stem], alignment: AlignmentCheck) -> list[RunWarning]:
    warnings = []
    for stem in stems:
        if stem.kind == "drums" and stem.rms_db_relative_to_mix < NEARLY_SILENT_DB:
            warnings.append(
                RunWarning(
                    code="drums_nearly_silent",
                    message="almost no drum content was found in this song",
                    value=stem.rms_db_relative_to_mix,
                    threshold=NEARLY_SILENT_DB,
                )
            )
        if stem.peak > CLIP_PEAK:
            warnings.append(
                RunWarning(
                    code="clipping_risk",
                    message=f"{stem.kind} peak exceeds 1.0 (stored unclipped as float)",
                    value=stem.peak,
                    threshold=CLIP_PEAK,
                )
            )
    if not alignment.passed:
        warnings.append(
            RunWarning(
                code="alignment_failed",
                message="stems are not aligned with the original within 1 ms",
                value=alignment.lag_ms,
                threshold=MAX_LAG_MS,
            )
        )
    return warnings


def run_separation(
    audio_path: Path,
    output_dir: Path,
    separator: Separator,
    *,
    write_accompaniment: bool = True,
    now: datetime | None = None,
) -> Path:
    """Separate one song and save the run. Returns the run directory.

    Output goes to `<run_id>.partial/` first and is renamed on success; on any failure
    the partial directory is removed so no incomplete output remains (FR-014).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    song, mix, warnings = load_song(audio_path)
    out = separator.separate(mix, song.sample_rate)
    alignment = check_alignment(song, mix, out)

    stem_audio: dict[StemKind, np.ndarray] = {"drums": out.drums}
    if write_accompaniment:
        stem_audio["accompaniment"] = out.accompaniment
    stems = [_stem(kind, audio, mix, song) for kind, audio in stem_audio.items()]
    warnings = warnings + _stem_warnings(stems, alignment)

    now = now or datetime.now().astimezone()
    run = SeparationRun(
        run_id=make_run_id(now, song.sha256),
        created_at=now.isoformat(timespec="seconds"),
        status="succeeded",
        song=song,
        separator=out.info,
        stems=stems,
        alignment=alignment,
        warnings=warnings,
    )

    final_dir = output_dir / run.run_id
    partial_dir = output_dir / f"{run.run_id}.partial"
    if final_dir.exists() or partial_dir.exists():
        raise PocError(f"run directory already exists: {final_dir}")
    partial_dir.mkdir()
    try:
        for stem in stems:
            sf.write(
                partial_dir / stem.path, stem_audio[stem.kind].T, song.sample_rate, subtype="FLOAT"
            )
        (partial_dir / "run.json").write_text(
            json.dumps(run.to_dict(), indent=2, ensure_ascii=False) + "\n"
        )
        (partial_dir / "evaluation.yaml").write_text(
            render_template(run.run_id, song_label=Path(audio_path).stem)
        )
        partial_dir.rename(final_dir)
    except BaseException:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise
    return final_dir
