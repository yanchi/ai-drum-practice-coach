import json

import numpy as np
import pytest
import soundfile as sf
from conftest import synth_drums, write_wav

from poc.audio.signal import rms_db_relative
from poc.recording.calibration import Calibration
from poc.recording.mix import build_evaluation_mix
from poc.recording.note_map import load_note_map

SR = 44100
COUNT_IN = 2 * SR
LATENCY_SEC = (0.010, 0.020)
SHIFT_SEC = COUNT_IN / SR + sum(LATENCY_SEC)
OFFSETS_MS = {36: 7.0, 38: 7.0, 42: -4.0}
CALIBRATION = Calibration(
    offsets_ms={"kick": 7.0, "snare": 7.0, "hihat": -4.0},
    note_offsets_ms=OFFSETS_MS,
    std_ms={"kick": 0.4, "snare": 0.7, "hihat": 0.7},
    counts={"kick": 8, "snare": 12, "hihat": 16},
    outliers=0,
)
INSTRUMENT = {36: "kick", 38: "snare", 42: "hihat", 48: "tom"}

# (time in the accompaniment / mix, MIDI note, velocity)
PLAYED = [
    (2.0, 36, 100),
    (2.0, 42, 80),
    (2.5, 38, 100),
    (3.0, 42, 80),
    (3.25, 38, 30),  # ghost
    (3.5, 36, 30),  # quiet kick: never a ghost
    (4.0, 48, 90),  # tom: not evaluated
]


@pytest.fixture
def dirs(tmp_path):
    rng = np.random.default_rng(0)
    run_dir = tmp_path / "runs" / "20261004-000000_abcdef12"
    run_dir.mkdir(parents=True)
    write_wav(run_dir, "accompaniment.wav", rng.normal(0, 0.1, (2, 8 * SR)), SR, "FLOAT")
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "stems": [{"kind": "drums", "rms_db_relative_to_mix": -6.0}],
            }
        )
    )

    rec_dir = tmp_path / "recordings" / "20261004-010000_abcdef12"
    rec_dir.mkdir(parents=True)
    hits, notes = [], []
    for t, note, velocity in PLAYED:
        audio_t = t + SHIFT_SEC  # where the hit sounds in the recording
        hits.append((audio_t, INSTRUMENT[note] if note != 48 else "snare", velocity))
        midi_t = audio_t - OFFSETS_MS.get(note, 0.0) / 1000
        notes.append({"time_sec": midi_t, "note": note, "velocity": velocity})
    notes.append({"time_sec": notes[0]["time_sec"] + 0.038, "note": 36, "velocity": 25})
    drums = synth_drums(hits, 8 + SHIFT_SEC + 1, SR, channels=2)
    write_wav(rec_dir, "drums.wav", drums, SR, "FLOAT")
    (rec_dir / "midi_notes.json").write_text(json.dumps(notes))
    (rec_dir / "recording.json").write_text(
        json.dumps(
            {
                "recording_id": rec_dir.name,
                "poc1_run_id": run_dir.name,
                "sample_rate": SR,
                "count_in_samples": COUNT_IN,
                "input_latency_sec": LATENCY_SEC[0],
                "output_latency_sec": LATENCY_SEC[1],
            }
        )
    )
    return rec_dir, run_dir


def build(dirs, **kwargs):
    rec_dir, run_dir = dirs
    return build_evaluation_mix(rec_dir, run_dir, "cal-1", CALIBRATION, load_note_map(), **kwargs)


def test_ground_truth_times_and_flags(dirs):
    _, gt = build(dirs)
    hits = [(round(h.time_sec, 4), h.instrument, h.ghost) for h in gt.hits]
    assert hits == [
        (2.0, "kick", False),
        (2.0, "hihat", False),
        (2.5, "snare", False),
        (3.0, "hihat", False),
        (3.25, "snare", True),
        (3.5, "kick", False),
    ]
    assert gt.source == "td17_midi"
    assert gt.target_kind == "evaluation_mix"
    assert gt.target_id == dirs[0].name
    assert gt.regions == [(1.5, 4.0)]
    assert gt.alignment.dropped_double_triggers == 1
    assert gt.alignment.calibration_id == "cal-1"
    assert gt.alignment.max_std_ms == pytest.approx(0.7)
    assert gt.alignment.stream_latency_ms == pytest.approx(30.0, abs=0.05)


def test_mix_audio_and_drum_level(dirs):
    mix_path, gt = build(dirs)
    mix, sr = sf.read(mix_path, always_2d=True)
    accompaniment, _ = sf.read(dirs[1] / "accompaniment.wav", always_2d=True)
    assert sr == SR
    assert mix.shape == accompaniment.shape
    assert sf.info(mix_path).subtype == "FLOAT"
    drums = (mix - accompaniment).T
    assert rms_db_relative(drums, mix.T) == pytest.approx(-6.0, abs=0.3)
    # the kick at 2.0 s sounds at 2.0 s in the mix (within 1 ms)
    onset = np.argmax(np.abs(drums[0, int(1.9 * SR) :]) > 0.01) / SR + 1.9
    assert onset == pytest.approx(2.0, abs=0.001)
    assert (dirs[0] / "groundtruth.json").exists()


def test_ghost_velocity_option(dirs):
    _, gt = build(dirs, ghost_velocity=20)
    assert not any(h.ghost for h in gt.hits)
