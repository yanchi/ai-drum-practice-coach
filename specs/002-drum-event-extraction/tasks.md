---

description: "Task list for PoC 2: Drum Event Extraction"
---

# Tasks: Drum Event Extraction (PoC 2)

**Input**: Design documents from `/specs/002-drum-event-extraction/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/cli.md](contracts/cli.md), [quickstart.md](quickstart.md)

**Tests**: 含める。plan.md の Testing と Constitution の Development Workflow (Lint / Test を通してから Human Review) のため。
TD-17 がなくても動くよう、合成音源・合成 MIDI でテストする。録音 (`poc record`) は実機で手動確認する。

**Organization**: User Story ごとにフェーズを分ける。TD-17 の準備 (Step 0) は US2 の最初に置く。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 並行して実行できる (別ファイルで、未完了のタスクに依存しない)
- **[Story]**: 対応する User Story (US1〜US3)

---

## Phase 1: Setup

- [X] T001 Add dependencies to `pyproject.toml`: `adtof-pytorch @ git+https://github.com/xavriley/ADTOF-pytorch@85c192e78f716ea0b111cc8a5ee4a8f6a3a4f8a9`, `librosa`, `pretty_midi`, `scipy`, `sounddevice`, `python-rtmidi`; run `uv lock` and `uv sync`; confirm `torch` stays at 2.14.1 and `numpy` at 2.4.x in `uv.lock`, and that `uv run python -c "import adtof_pytorch, librosa, pretty_midi, scipy, sounddevice, rtmidi"` succeeds
- [X] T002 Create packages `poc/transcription/__init__.py` and `poc/recording/__init__.py` (empty)
- [X] T003 [P] Extend `tests/conftest.py` with `synth_drums(hits, sec, sr)` that renders synthetic hits from `(time_sec, instrument, velocity)` tuples (kick = 60 Hz decaying sine, snare = decaying noise + 200 Hz tone, hihat = decaying high-passed noise, amplitude ∝ velocity / 127), and a `FakeTranscriber` that returns a given list of `DrumEvent` and a `TranscriberInfo` with `method="fake"`

**Checkpoint**: 依存が入り、既存のテスト (PoC 1) がすべて通る

---

## Phase 2: Foundational

- [X] T004 [P] Add to `poc/domain.py` (data-model.md): `Instrument` literal (`kick` / `snare` / `hihat` / `tom` / `cymbal`), `EVALUATED_INSTRUMENTS = ("kick", "snare", "hihat")`, frozen dataclasses `DrumEvent`, `TranscriptionInput`, `TranscriberInfo`, `TranscriptionRun` (with `to_dict()` matching data-model, `schema_version: 1`), `GroundTruthHit`, `MidiAudioAlignment`, `GroundTruth` (with `to_dict()` / `from_dict()`), `InstrumentMetrics`; no ML / device library imports
- [X] T005 [P] Create `poc/transcription/base.py` with `Transcriber` Protocol: `transcribe(audio_path: Path) -> tuple[list[DrumEvent], TranscriberInfo]`
- [X] T006 Add subcommands to `poc/cli.py` with arguments exactly as `contracts/cli.md`: `transcribe`, `record` (`--check`, `--list-devices`, `--device`, `--midi-port`), `evaluate` (`recording_dir` or `--annotation`, `--tolerance-ms`, `--ghost-velocity`), `summarize-events`, `check-events`; handlers raise `NotImplementedError` for now

**Checkpoint**: `uv run poc --help` に 8 個のサブコマンドが出る

---

## Phase 3: User Story 1 - Drum Stem から打撃イベントを取り出す (Priority: P1) 🎯 MVP

**Goal**: PoC 1 の run から打撃イベントを推定し、`transcription.json` / `check.wav` / `events.mid` を出す

**Independent Test**: `uv run poc transcribe output/runs/<run_id>` を実行し、`check.wav` を聴いて Kick / Snare / HiHat がおおむね合っていることを確認する

### Tests for User Story 1

- [X] T007 [P] [US1] Write `tests/unit/test_render.py`: `render_check_wav` places each click within ±1 sample of the event time, the dominant frequency of each click is 400 Hz / 800 Hz / 1.6 kHz for kick / snare / hihat (woodblock-like, changed 2026-10-04), tom and cymbal produce no click, the output has the original's length and sample rate; `write_events_midi` writes GM notes 36 / 38 / 42 / 47 / 49 with velocity `round(strength * 127)` (min 1) at the event times (read back with pretty_midi)
- [X] T008 [P] [US1] Write `tests/pipeline/test_transcribe_run.py` with `FakeTranscriber` and a fake PoC 1 run directory (`run.json`, `drums.wav`, `accompaniment.wav`, input song WAV): `--input drum_stem` / `mix` / `accompaniment` pick `drums.wav` / `song.path` / `accompaniment.wav`; output directory contains `transcription.json` (fields per data-model, events sorted by time, `event_counts`), `events.mid`, `check.wav`; missing `accompaniment.wav` → `UserInputError`; zero events → warning `no_events`; failure leaves no `.partial` directory
- [X] T009 [P] [US1] Write `tests/unit/test_check_events.py`: identical transcriptions → PASS; one event moved by 10 ms → FAIL with `mismatches=1`; different `audio_sha256` or thresholds → `UserInputError`
- [X] T010 [P] [US1] Write `tests/integration/test_adtof.py` marked `@pytest.mark.slow`: a 20 s synthetic 8-beat pattern from `synth_drums` (kick on 1 and 3, snare on 2 and 4, hihat on eighths, 100 BPM) transcribed by `AdtofTranscriber` yields events for all three instruments, at least 70% of synthetic hits per instrument have an estimate within 50 ms (sanity check, not a success criterion), and two runs give identical events

### Implementation for User Story 1

- [X] T011 [US1] Implement `poc/transcription/adtof_adapter.py`: `AdtofTranscriber(thresholds=None)` implementing `Transcriber` on CPU — build the model with `create_frame_rnn_model(calculate_n_bins())`, load packaged weights with `load_pytorch_weights` (path from `get_default_weights_path()`), get activations from `load_audio_for_model(path)`, run `NotePeakPickingProcessor` per class with `FRAME_RNN_THRESHOLDS` and the same parameters as `PeakPicker`, map `LABELS_5 = [35, 38, 47, 42, 49]` to `kick / snare / tom / hihat / cymbal`, set `strength` to the activation at the peak frame (clipped to 0–1), and fill `TranscriberInfo` (version = package version + git commit `85c192e`, params = thresholds, fps 100, peak picking values) (research R-01〜R-03)
- [X] T012 [P] [US1] Implement `poc/transcription/render.py`: `render_check_wav(original_audio, sr, events) -> np.ndarray` (30 ms sine clicks with a 5 ms fade, volume `0.3 + 0.5 * strength`, mixed onto the original at −6 dB, float32) and `write_events_midi(events, path)` with pretty_midi (research R-14)
- [X] T013 [US1] Implement `poc/transcription/run.py`: `run_transcription(poc1_run_dir, kind, output_dir, transcriber) -> Path` — resolve the input audio from the PoC 1 `run.json`, measure stages with `Stopwatch` (`load` / `transcribe` / `write`), write `transcription.json`, `events.mid`, `check.wav` (rendered on the PoC 1 input decoded with `load_song`) into `<id>.partial/` and rename on success (reuse PoC 1 patterns from `poc/evaluation/run.py`)
- [X] T014 [US1] Implement `compare_transcriptions(a, b)` in `poc/transcription/run.py` and wire `transcribe` and `check-events` in `poc/cli.py` (output formats from `contracts/cli.md`)
- [X] T015 [US1] Manually run `uv run poc transcribe` on all 5 PoC 1 runs, play each `check.wav`, and note the processing time from `transcription.json` (quickstart §1)

- [X] T047 [US1] (2026-10-04, research R-16) Add `--thresholds kick=0.12,hihat=0.12` to `poc transcribe` (unspecified instruments keep the ADTOF defaults): parse in `poc/cli.py`, accept a per-instrument dict in `AdtofTranscriber` (`poc/transcription/adtof_adapter.py`), record the thresholds actually used in `transcription.json`; tests in `tests/unit/test_thresholds.py` (parsing, unknown instrument / out-of-range value → `UserInputError`, override mapping)

**Checkpoint**: 原曲から打撃イベントが取り出せ、耳で確認できる (MVP)

---

## Phase 4: User Story 2 - 電子ドラムの演奏を正解にして精度を測る (Priority: P2)

**Goal**: TD-17 で録音した演奏を正解にして、楽器ごとの P / R / F1 とタイミング誤差を出す。手動アノテーションでも評価できる

**Independent Test**: 1 曲を `poc record` で録音して `poc evaluate` を実行し、楽器別の指標・タイミング誤差・伴奏に残ったドラムの検出数が出る

### Step 0: TD-17 の準備 (実機)

- [X] T016 [US2] Developer: install Roland TD-17 Driver Ver.1.0.3 for macOS, set `SETUP → USB → USB Driver Mode = VENDOR`, connect TD-17 via USB, select an acoustic-style preset kit (quickstart §0). **If the driver does not work on macOS 15, stop and return to Human Review** (plan Implementation Notes)

### Tests for User Story 2

- [X] T017 [P] [US2] Write `tests/unit/test_note_map.py`: default map from `poc/recording/td17_note_map.yaml` maps 36 → kick, 38 / 40 / 37 → snare, 42 / 22 / 46 / 26 / 44 → hihat (44 = pedal chick counts as hihat), tom and cymbal notes → `None` (ignored); unknown notes → `None` with a warning; velocity-0 note-on is treated as note-off
- [X] T018 [P] [US2] (changed 2026-10-04: calibration instead of aligning onsets in the performance, research R-06) Write `tests/unit/test_calibration.py`: synthetic pads hit one at a time with known per-note delays → per-note and per-instrument offsets recovered, std ≤ 0.5 ms; missing instrument or jitter > 1 ms → `CalibrationError`; JSON round trip; and `test_drop_double_triggers` in `tests/unit/test_note_map.py`
- [X] T019 [P] [US2] Write `tests/unit/test_mix.py`: drums shifted earlier by `stream_latency` samples; drum gain makes drum RMS relative to the mix equal the PoC 1 `rms_db_relative_to_mix` within 0.1 dB; ground-truth times equal aligned MIDI times minus latency; `regions` = first / last hit ± 0.5 s; snare / hihat with velocity < 40 are `ghost=True`, kick never; tom / cymbal notes are excluded; output is float32 at 44.1 kHz with the accompaniment's length
- [X] T020 [P] [US2] Write `tests/unit/test_matching.py`: per-instrument one-to-one matching within ±50 ms (two estimates near one hit → 1 TP + 1 FP; one estimate between two hits → 1 TP + 1 FN; 60 ms away → FP + FN); precision / recall / F1 including null when denominators are 0; timing `mae` / `median_abs` / `p95_abs` / `median_signed`; ghost hits excluded from TP/FN and reported separately; estimates outside `regions` ignored; `strength_spearman` computed when TP ≥ 5 and velocities exist, else null
- [X] T021 [P] [US2] Write `tests/unit/test_groundtruth.py`: `annotation.yaml` + `hits.csv` with labels `k` / `s` / `h` / `sg` / `hg` → `GroundTruth(source="manual")` with ghost flags; hits outside regions are dropped; unknown labels, overlapping regions, or a missing PoC 1 run → `UserInputError` naming the file and line
- [X] T022 [P] [US2] Write `tests/pipeline/test_events_eval.py` with `FakeSeparator` (PoC 1 conftest) and `FakeTranscriber`: given a fake recording directory (`recording.json`, `drums.wav` from `synth_drums`, `midi_notes.json`) and a fake PoC 1 run, `evaluate_recording` writes `mix.wav` and `groundtruth.json` into the recording directory and `evaluation.json` with `drum_stem` results and `residual_drum_hits`; alignment failure → `AlignmentError` (exit 1) and no evaluation directory
- [X] T023 [P] [US2] Write `tests/unit/test_events_summary.py`: SC-001 pooled F1 per instrument ≥ 0.80 over `td17_midi` evaluations; SC-002 median / p95 thresholds; SC-003 counts distinct PoC 1 runs (≥ 5 td17) and manual evaluations (≥ 1), else INSUFFICIENT; SC-004 normalized time; SC-006 required fields; SC-008 all `residual_std_ms ≤ 1.0`; SC-009 manual F1 ≥ td17 F1 − 0.10 reported as "reference"

### Implementation for User Story 2

- [X] T024 [P] [US2] Create `poc/recording/td17_note_map.yaml` (research R-08) and `poc/recording/note_map.py` (`load_note_map(path=None)`, `instrument_for(note)`)
- [X] T025 [P] [US2] Implement `poc/recording/devices.py`: list audio devices (sounddevice) and MIDI input ports (python-rtmidi), find a device / port by case-insensitive substring (default `"TD-17"`), and raise `UserInputError` with driver / VENDOR-mode guidance when not found
- [X] T026 [US2] Implement `poc/recording/record.py`: `record_play_along(poc1_run_dir, device, midi_port, output_dir)` — open one `sounddevice.Stream` (duplex, 44.1 kHz, stereo) on the TD-17, play a 4-beat count-in click then `accompaniment.wav`, capture input into memory, receive MIDI with an rtmidi callback timestamped by `time.perf_counter()` relative to the stream start, stop at the end or on Ctrl+C, and save `drums.wav` (float32), `midi_notes.json`, `recording.json` (device names, sample rate, block size, stream input / output latency, note map) atomically (research R-05)
- [X] T027 [US2] Implement `poc/recording/check.py` (`--check`): play a 5 s test tone while recording silence and report PASS when recorded RMS is ≥ 40 dB below the played signal and their correlation is < 0.1; then prompt to hit each pad and print received note → instrument (research R-07)
- [X] T028 [US2] Wire `record` (`--list-devices`, `--check`, recording) in `poc/cli.py`
- [X] T029 [US2] Developer: run `uv run poc record --list-devices` and `uv run poc record --check` on the real TD-17; fix the note map if pads send different notes. **If the loopback check fails, stop and adjust the TD-17 USB settings before recording**
- [X] T049 [US2] (added 2026-10-04) Implement `poc record --calibrate` in `poc/recording/record.py` (`calibration_playback` with a 60 BPM guide click and the hit schedule, `record_calibration`) sharing `capture` / `save_capture` with the play-along recording; also `--max-seconds` for test recordings; wire in `poc/cli.py`
- [X] T050 [US2] Developer: run `uv run poc record --calibrate` on the TD-17 (result: std ≤ 0.76 ms for all instruments, SC-008)
- [X] T030 [US2] (changed 2026-10-04, research R-06) Implement `poc/recording/calibration.py` (`measure_calibration`, `Calibration`) and `drop_double_triggers` in `poc/recording/note_map.py`; remove the onset-alignment approach (`align.py`)
- [X] T031 [US2] Implement `poc/recording/mix.py`: `build_evaluation_mix(recording_dir, poc1_run_dir, calibration, ghost_velocity=40) -> (mix_path, GroundTruth)` — drop double triggers, convert MIDI times with the calibration (`offset_sec(note, instrument)`), shift drums by the stream latency, scale to the PoC 1 drum level, add to the accompaniment (float32 44.1 kHz), and build `GroundTruth(source="td17_midi")` with regions, ghost flags and a `MidiAudioAlignment` (calibration id, offsets used, max std, dropped double triggers); write `mix.wav` and `groundtruth.json` (research R-10)
- [X] T032 [P] [US2] Implement `poc/evaluation/matching.py`: `evaluate_events(groundtruth, events, tolerance_ms) -> dict[str, InstrumentMetrics]` and ghost-note stats using `scipy.optimize.linear_sum_assignment` on candidate pairs within the tolerance (cost = |Δt|, pairs outside the tolerance forbidden), and `scipy.stats.spearmanr` for strength vs velocity (research R-11)
- [X] T033 [P] [US2] Implement `poc/evaluation/groundtruth.py`: `load_annotation(annotation_yaml) -> GroundTruth` (research R-13)
- [X] T034 [US2] Implement `poc/evaluation/events_eval.py`: `evaluate_recording(recording_dir, ...)` — align, build the mix, separate the mix with PoC 1 `run_separation` (output to `output/runs/`), transcribe its `drum_stem`, transcribe the original `accompaniment` for `residual_drum_hits` (hits inside the regions), evaluate, and write `output/evaluations/<id>/evaluation.json` atomically; `evaluate_annotation(annotation_yaml, ...)` — transcribe the PoC 1 run's `drum_stem` and evaluate against the manual ground truth
- [X] T035 [US2] Wire `evaluate` in `poc/cli.py` and print a per-instrument table (P / R / F1 / median_abs / p95_abs ms)
- [X] T036 [US2] Implement `poc/evaluation/events_summary.py` (SC judgements as `contracts/cli.md`, `poc2_summary.md` / `poc2_summary.csv`) and wire `summarize-events` in `poc/cli.py`
- [X] T048 [US2] (research R-16) Split `AdtofTranscriber` into `activations()` and `events_from_activations()`, and implement `poc tune-thresholds` in `poc/evaluation/tuning.py`: recompute the drum stem activations once per song, re-run peak picking for thresholds 0.06–0.30 (step 0.02), pooled F1 per threshold, leave-one-song-out choice (middle of tied best thresholds), `output/reports/poc2_thresholds.md` / `.json`; tests in `tests/unit/test_tuning.py`
- [X] T051 [US2] (added 2026-10-04, from the first real evaluation) Calibration onset at 2% of the rise (15% read the kick / snare head ~10 ms late); drop TD-17 double triggers: retrigger chains within 40 ms of the previous note and weak bounces (≤ 60% velocity) within 80 ms; ghost notes for the snare only (spec Clarifications); transcription ids include the input kind; separate evaluation mixes into `output/eval_runs/`
- [X] T037 [US2] Developer pilot: record and evaluate one song; check the velocity distribution of snare / hihat (adjust the ghost threshold 40 if needed), double triggers dropped, and the time spent (SC-007)

**Checkpoint**: 1 曲で録音から評価まで通る

---

## Phase 5: User Story 3 - Drum Stem を使う効果を確かめる (Priority: P3)

**Goal**: 分離前の評価用の曲から直接推定した結果も、同じ正解で評価して並べる

**Independent Test**: `poc evaluate` の結果に `drum_stem` と `mix` の 2 つの指標が並ぶ

- [X] T038 [P] [US3] Extend `tests/pipeline/test_events_eval.py`: `evaluation.json` `results` contains both `drum_stem` and `mix`; the annotation path also evaluates `mix` (the PoC 1 input song)
- [X] T039 [US3] Update `poc/evaluation/events_eval.py` to also transcribe and evaluate the `mix` input, and `poc/evaluation/events_summary.py` / `poc/cli.py` to show a drum_stem vs mix F1 comparison per instrument

**Checkpoint**: すべての User Story が動作する

---

## Phase 6: Polish & Evaluation

- [x] T040 [P] Update `README.md` with a "PoC 2: Drum Event Extraction" section linking to `specs/002-drum-event-extraction/quickstart.md`
- [x] T041 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`, `uv run pytest -m slow`; fix failures
- [x] T042 Follow `specs/002-drum-event-extraction/quickstart.md` end to end and fix steps that do not work as written
- [x] T043 Developer: record and evaluate all 5 songs of the evaluation set with TD-17, noting the time spent per song (SC-003, SC-007) — NO. NEW YORK / B・BLUE / ONLY YOU / WORKING MAN / PLASTIC BOMB done (research R-17, R-19). PLASTIC BOMB replaces 誇り高きものへ (spec Clarifications 2026-10-04). Time per song for the last three songs is estimated from the timestamps (research R-19)
- [ ] T044 Developer: manually annotate 1〜2 PoC 1 songs (3 sections × 4 bars) and run `poc evaluate --annotation` (SC-003, SC-009)
- [x] T045 Run `poc transcribe` twice on one PoC 1 run and `poc check-events` (SC-005) — B・BLUE: 1683 events each, 0 mismatches, PASS (research R-19)
- [ ] T046 Run `poc tune-thresholds`, then `poc summarize-events` (SC-001 uses the leave-one-out F1 with tuned thresholds; also report the default-threshold F1), and write `docs/research/poc2-evaluation.md`: SC-001〜SC-009, per-instrument metrics for drum_stem vs mix, residual drum hits, ghost notes, strength correlation, alignment quality, processing time / memory, limitations (electronic drum timbre, rock only, small manual set), and a Go/No-Go recommendation (no audio or song file paths) — draft written; waiting for T044 to settle SC-003 / SC-009 and for the threshold decision

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup → Foundational**: 順番に
- **US1 (Phase 3)**: Foundational の後。MVP
- **US2 (Phase 4)**: US1 の後 (`run_transcription` を使う)。T016 (TD-17 の準備) は US1 と並行して進めてよい
- **US3 (Phase 5)**: US2 の後 (`events_eval.py` を拡張)
- **Polish (Phase 6)**: 全 User Story の後。T043 / T044 / T045 → T046

### Within User Story 2

- 実機なしで進められる部分 (T017〜T025, T030〜T036) と、実機が必要な部分 (T016, T026〜T029, T050, T037) がある。実機が使えない間も前者を進められる
- T029 (実機での `--check`) が通るまで、本番の録音 (T037, T043) をしない

### Parallel Opportunities

- Phase 2: T004 / T005 は並行可能
- US1: テスト T007〜T010 は並行可能。T012 は T011 と並行可能
- US2: テスト T017〜T023 は並行可能。T024 / T025 / T032 / T033 は並行可能

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Setup → Foundational → US1
2. **止めて確認**: 5 曲の `check.wav` を聴く。明らかに使えない場合は、TD-17 の録音系を作る前に Human Review で方式を見直す
3. 並行して T016 (TD-17 のドライバ) を進めておく

### Incremental Delivery

1. US1 → 原曲から打撃イベント (MVP)
2. US2 → 1 曲でパイロット評価 (T037) → 5 曲の本評価
3. US3 → 分離ありなしの比較
4. Polish → レポート → Go/No-Go

## Notes

- 楽曲・伴奏・録音・正解データ・抽出結果はコミットしない (`data/`, `output/` は `.gitignore` 済み)
- 新しい依存を追加する場合は Human Review を受ける
