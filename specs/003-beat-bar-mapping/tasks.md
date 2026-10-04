---

description: "Task list for PoC 3: Beat / Downbeat Analysis and Bar Mapping"
---

# Tasks: Beat / Downbeat Analysis and Bar Mapping (PoC 3)

**Input**: Design documents from `/specs/003-beat-bar-mapping/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/cli.md](contracts/cli.md), [quickstart.md](quickstart.md)

**Tests**: 含める。plan.md の Testing と Constitution の Development Workflow (Lint / Test を通してから Human Review) のため。
Beat This! と TD-17 がなくても動くよう、合成した拍の列・小節の頭の活性値・打撃イベント・MIDI でテストする。拍を叩く録音 (`poc record --tap-beats`) は実機で手動確認する。

**Organization**: User Story ごとにフェーズを分ける。US1 と US2 はどちらも P1 で、US2 は US1 の BeatGrid を使う。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 並行して実行できる (別ファイルで、未完了のタスクに依存しない)
- **[Story]**: 対応する User Story (US1〜US4)

---

## Phase 1: Setup

- [X] T001 Create package `poc/mapping/__init__.py` (empty); confirm `uv run pytest` and `uv run ruff check .` pass on the branch before any change (no new dependencies: `beat-this` 1.1.0 is already in `pyproject.toml`)
- [X] T002 [P] Add to `tests/conftest.py`: `synthetic_beats(bpm, sec, start=0.5, jitter_ms=0, seed=0)` returning beat times, `downbeat_activation(n_beats, phase=0, flips=None, noise=0.0, seed=0)` returning a per-beat activation array (high on beats where `(i + phase) % 4 == 0`, with optional `flips=[(from_beat, new_phase)]` to simulate a phase change), and a `FakeBeatEstimator` returning given beats / downbeats / activations with `method="fake"`

**Checkpoint**: 既存のテスト (PoC 1・2) がすべて通る

---

## Phase 2: Foundational

- [X] T003 [P] Add to `poc/domain.py` (data-model.md): frozen dataclasses `Beat`, `BeatGrid` (with `to_dict()` / `from_dict()`, `schema_version: 1`), `BeatPosition`, `ReferencePerformance` (`to_dict()` / `from_dict()`), `BeatGroundTruth` (`to_dict()` / `from_dict()`), `BeatMetrics`; `GRID_POSITIONS = ("0", "1/4", "1/3", "1/2", "2/3", "3/4")`; no ML / device library imports
- [X] T004 [P] Create `poc/beat/base.py` with `BeatEstimate` (frozen dataclass: `beats: list[float]`, `downbeats: list[float]`, `beat_times_activation: list[float]` = downbeat activation sampled at each beat, `info: dict` with `method` / `version` / `checkpoint` / `device`) and `BeatEstimator` Protocol: `estimate(signal: np.ndarray, sr: int) -> BeatEstimate`
- [X] T005 Create `poc/beat/beat_this_adapter.py` (research R-01): `BeatThisEstimator(checkpoint="final0", device="cpu")` that runs `beat_this.inference.Audio2Frames` once to get beat / downbeat logits, converts them with the `minimal` `Postprocessor` to beat / downbeat times, and samples `sigmoid(downbeat_logits)` at each beat frame (50 fps); Beat This! types stay inside this module. Move `detect_beats` from `poc/beat/beats.py` here as a thin wrapper over `BeatThisEstimator` and update `poc/beat/beats.py` and `tests/integration/test_beat_this.py` to import it from the new module
- [X] T006 Create `poc/beat/grid.py` and move `fill_beat_gaps` and `drum_offset_sec` from `poc/beat/beats.py` into it unchanged; update `poc/beat/beats.py` and `tests/unit/test_beats.py` imports; `uv run pytest` must stay green (the `poc record --click` behaviour must not change)
- [X] T007 Add subcommands to `poc/cli.py` with arguments exactly as `contracts/cli.md`: `beats` (`--input {mix,drum_stem}`, `--no-regularize`, `--no-offset`, `--output-dir`), `map`, `bars`, `evaluate-beats` (`--taps` / `--annotation`, `--transcription`, `--tolerance-ms`, `--output-dir`), `summarize-beats`, `check-beats`; add `--tap-beats` to `record` and `--beats` to `annotate`; new handlers raise `NotImplementedError` for now

**Checkpoint**: `uv run poc --help` に新しいサブコマンドが出て、既存のテストが通る

---

## Phase 3: User Story 1 - 曲の拍と小節の位置を推定する (Priority: P1) 🎯 MVP

**Goal**: PoC 1 の run から BeatGrid (補った拍・整理した小節の頭・位置合わせ・BPM・拍子) と確認用の `check.wav` を作る

**Independent Test**: `uv run poc beats output/runs/<run_id>` で `beatgrid.json` と `check.wav` ができ、聴くと拍のクリックが曲に合い、高い音が小節の頭で鳴る

### Tests for User Story 1

- [X] T008 [P] [US1] Create `tests/unit/test_grid.py` and test `fill_beat_gaps` with a local median (research R-02): a tempo that drifts from 160 to 175 BPM still gets single missing beats filled; gaps longer than 4 beats are left and reported; filled beats are flagged as inferred
- [X] T009 [P] [US1] In `tests/unit/test_grid.py`, test `regularize_downbeats(activation, meter=4)` (research R-03): (a) clean activation → downbeats every 4 beats with the right phase; (b) a 2-beat phase shift lasting 32 beats (WORKING MAN case) is followed, and the change point is reported in `phase_changes`; (c) isolated spurious peaks (one high value inside a bar, PLASTIC BOMB case) do not create a phase change; (d) `meter != 4` returns the raw downbeats with a warning
- [X] T010 [P] [US1] In `tests/unit/test_grid.py`, test `estimate_meter(beats, raw_downbeats)` (mode of beats per bar), `bpm_overall(beats)` and `bpm_sections(beats, downbeats, bars_per_section=16)`
- [X] T011 [P] [US1] Create `tests/pipeline/test_beats_run.py`: `run_beats(poc1_run_dir, ..., estimator=FakeBeatEstimator)` on a fake PoC 1 run (short synthetic `drums.wav` / song via `write_wav`, plus a fake drum stem `transcription.json` whose kicks are 15 ms before the beats) writes `beatgrid.json` with `offset.applied_ms ≈ -15`, `downbeat_source == "regularized"`, inferred beats flagged, and `check.wav`; `--no-offset` gives `applied_ms == 0`; `--no-regularize` gives `downbeat_source == "raw"`; a missing transcription without `--no-offset` raises `UserInputError`

### Implementation for User Story 1

- [X] T012 [US1] In `poc/beat/grid.py`, change `fill_beat_gaps` to use the median interval of the surrounding 16 beats and to return `(times, inferred_flags)`; keep a wrapper with the old signature for `poc/beat/beats.py` (`click_beats`) so `poc record --click` is unchanged
- [X] T013 [US1] In `poc/beat/grid.py`, implement `regularize_downbeats(activation: list[float | None], meter: int = 4, switch_penalty: float = 4.0) -> tuple[list[int], list[int]]` returning the indices of downbeats and of phase-change beats: Viterbi over phases 0..3, emission = log of activation for phase 0 and log(1 − activation) otherwise (inferred beats with `None` activation emit equally), transition = advance by one phase with cost 0, any other phase with cost `switch_penalty`; tune `switch_penalty` only with the synthetic tests in T009
- [X] T014 [US1] In `poc/beat/grid.py`, implement `estimate_meter`, `bpm_overall`, `bpm_sections`, and `find_gaps(beats, factor=1.5)` (spans without beats, research R-05 step 5)
- [X] T015 [US1] Create `poc/beat/run.py`: `run_beats(poc1_run_dir, input_kind, output_dir, estimator, regularize=True, offset=True, transcriptions_dir=Path("output/transcriptions"))` — resolve the input (`mix` = song path in `run.json` decoded with `poc.audio.decode.load_song`; `drum_stem` = `drums.wav`), call the estimator, fill gaps, regularize, compute the drum offset from `latest_drum_stem_onsets` (`poc/beat/beats.py`) and shift beats and both downbeat lists, build `BeatGrid`, record timings / peak memory / environment like `poc/transcription/run.py`, write `beatgrid.json` and `check.wav` (song at −6 dB + `add_beat_clicks` from `poc/recording/record.py`) into a `.partial` directory and rename it; `beatgrid_id` = `<YYYYmmdd-HHMMSS>_<input>_<sha256[:8]>`
- [X] T016 [US1] Implement the `beats` handler in `poc/cli.py`: print the directory to stdout and BPM / meter / filled beats / changed downbeats / offset to stderr
- [ ] T017 [US1] Developer: run `uv run poc beats` on PLASTIC BOMB, WORKING MAN and ONLY YOU, listen to `check.wav` (downbeat accent at 0:00–0:30, 1:06–1:58 and throughout respectively) and compare with `--no-regularize`; note what you hear in `specs/003-beat-bar-mapping/research.md` (new section R-12)

**Checkpoint**: 5 曲の BeatGrid ができ、整理の効果を耳で確認できた

---

## Phase 4: User Story 2 - 打撃イベントを小節・拍に対応付ける (Priority: P1)

**Goal**: BeatGrid と PoC 2 の打撃イベントから `reference.json` を作り、小節の範囲で取り出せる

**Independent Test**: `uv run poc map <beatgrid_dir> <transcription_dir>` のあと `uv run poc bars <reference_dir> 12 13` で、12〜13 小節目の打撃が拍の位置つきで並ぶ

### Tests for User Story 2

- [ ] T018 [P] [US2] Create `tests/unit/test_reference.py` for `position_of(t, beats, downbeats)` (research R-05): an event 20 ms before a downbeat maps to `beat 1`, grid `"0"`, `deviation_ms ≈ -20` of the next bar; 16th notes map to `"1/4"` / `"1/2"` / `"3/4"`; triplets map to `"1/3"` / `"2/3"`; events before the first downbeat get `bar 0`; events inside a beat gap get `bar None` and `unmapped_reason == "no_beats"`; tempo drift does not change the grid positions
- [ ] T019 [P] [US2] In `tests/unit/test_reference.py`, test `build_reference(beatgrid, transcription)` rejects different `poc1_run_id` (`UserInputError`), keeps tom / cymbal events, and `events_in_bars(reference, first, last)` returns only those bars

### Implementation for User Story 2

- [ ] T020 [US2] Create `poc/mapping/reference.py` with `position_of`, `build_reference(beatgrid: BeatGrid, transcription: dict) -> ReferencePerformance`, `events_in_bars`, and `run_map(beatgrid_dir, transcription_dir, output_dir)` writing `reference.json` via a `.partial` directory; `reference_id` = `<YYYYmmdd-HHMMSS>_<beatgrid_id suffix>`
- [ ] T021 [US2] Implement the `map` and `bars` handlers in `poc/cli.py` (`bars` prints the table in `contracts/cli.md`)

**Checkpoint**: 1 曲の Reference Performance Data を作り、任意の小節の打撃を確認できた

---

## Phase 5: User Story 3 - 拍・小節の推定と対応付けの正しさを測る (Priority: P2)

**Goal**: 拍を叩いた正解 (曲全体) と手で付けた正解 (区間) で BeatGrid を評価し、5 曲を集計して SC を判定する

**Independent Test**: 1 曲で `poc record --tap-beats` → `poc evaluate-beats --taps` を実行し、拍・小節の頭の F-measure、BPM の誤差、拍子、打撃の割り当ての一致率が出る

### Tests for User Story 3

- [ ] T022 [P] [US3] Create `tests/unit/test_taps.py` for `taps_to_groundtruth(notes, note_map, calibration, shift_sec)` (research R-06): hi-hat notes (including pedal 44) become beats; a hi-hat with a kick within ±50 ms becomes a downbeat; calibration offsets per note are applied; double triggers are dropped (reuse `drop_double_triggers`); an interval more than 35% off the local median of 8 intervals produces a warning with its time; the region is from the first to the last beat
- [ ] T023 [P] [US3] Create `tests/unit/test_beat_groundtruth.py` for `load_beat_annotation(annotation_yaml)`: reads `beat_regions` and `beats.csv` (`b` / `d`), keeps only rows inside the regions, rejects unknown labels and missing `beat_regions` (`UserInputError`); and for `write_beats(path, csv_text)` in `poc/evaluation/annotate.py` (validation like `write_hits`)
- [ ] T024 [P] [US3] Create `tests/unit/test_beats_eval.py` for `evaluate_beatgrid(beatgrid_variant, groundtruth, tolerance_ms=70)`: F-measure with one-to-one matching; estimates outside the regions are ignored; BPM error % and meter match; `mapping_accuracy` counts an event as correct only when the bar start (±70 ms), beat in bar and grid all match, and is unaffected by a different first-bar numbering between estimate and truth; `tap_jitter(taps, manual)` returns median / p95 of matched differences
- [ ] T025 [P] [US3] Create `tests/unit/test_beats_summary.py` for `summarize_beats`: latest evaluation per song, pooled beat / downbeat F-measure, SC-001〜SC-005 judgements with `INSUFFICIENT` when fewer than 5 songs or no manual annotation

### Implementation for User Story 3

- [ ] T026 [US3] Create `poc/recording/taps.py` with `taps_to_groundtruth` (T022) returning `BeatGroundTruth` with `source="td17_taps"` and the alignment record
- [ ] T027 [US3] In `poc/recording/record.py`, add `record_beat_taps(poc1_run_dir, device_name, midi_port_name, output_dir)`: playback = count-in + the decoded **original song** (no beat clicks), reuse `capture`; save `recording.json` (`kind: "beat_taps"`), `midi_notes.json` and `beat_groundtruth.json` (no drum audio); print tapping warnings to stderr; wire `record --tap-beats` in `poc/cli.py`
- [ ] T028 [US3] Developer: pilot `uv run poc record output/runs/20261004-004951_3e21c73e --tap-beats` (B・BLUE); check the warnings and that the beats sound right (render them with `add_beat_clicks` onto the song in a scratch WAV)
- [ ] T029 [US3] Create `poc/evaluation/beat_groundtruth.py` with `load_beat_annotation` (T023); add `write_beats` and a `--beats` mode to `poc/evaluation/annotate.py` (`annotation_config` returns `beat_regions` and existing `beats.csv`; `POST /beats` saves)
- [ ] T030 [US3] In `poc/evaluation/annotator.html`, add a beat mode (enabled when `/config` has `mode: "beats"`): only the full-waveform lane is clickable, click = beat `b`, Shift+click = downbeat `d`, marks snap to the attack start like the drum lanes, the region list comes from `beat_regions`, and Save posts to `beats`
- [ ] T031 [US3] Create `poc/evaluation/beats_eval.py`: `evaluate_beatgrid`, `tap_jitter`, and `run_evaluate_beats(beatgrid_dir, taps_dir | annotation_yaml, transcription_dir, tolerance_ms, output_dir)` that rebuilds the `raw` / `regularized` / `regularized_offset` variants from the stored BeatGrid fields (no model rerun), computes the mapping accuracy with `poc/mapping/reference.py` against the ground-truth grid, adds `tap_jitter_ms` when a manual `beats.csv` exists for the same run, and writes `evaluation.json`; wire `evaluate-beats` in `poc/cli.py`
- [ ] T032 [US3] Create `poc/evaluation/beats_summary.py` (`summarize_beats` → `output/reports/poc3_summary.md` / `.csv`, SC-001〜SC-009) and `compare_beatgrids` for `check-beats` (exact match of beats and downbeats); wire `summarize-beats` and `check-beats` in `poc/cli.py`

**Checkpoint**: 1 曲で叩いた正解による評価が出て、集計に SC の判定が出る

---

## Phase 6: User Story 4 - 原曲と Drum Stem のどちらで拍を推定するのがよいか確かめる (Priority: P3)

**Goal**: 同じ正解で、原曲入力と Drum Stem 入力の BeatGrid の指標を並べる

**Independent Test**: 1 曲で `poc beats --input drum_stem` の BeatGrid を `evaluate-beats` にかけ、原曲入力と同じ形式の指標が出る

- [ ] T033 [P] [US4] In `tests/pipeline/test_beats_run.py`, add a case for `input_kind="drum_stem"` (input path is `drums.wav`, `input.kind` recorded) and in `tests/unit/test_beats_summary.py` a case where the summary shows mix vs drum_stem F-measure side by side
- [ ] T034 [US4] In `poc/evaluation/beats_summary.py`, group evaluations by `input.kind` and add a "mix vs drum stem" table to `poc3_summary.md`

---

## Phase 7: Polish & Evaluation

- [ ] T035 [P] Update `README.md` with a "PoC 3: Beat / Bar Mapping" section linking to `specs/003-beat-bar-mapping/quickstart.md`
- [ ] T036 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`, `uv run pytest -m slow`; fix failures
- [ ] T037 Follow `specs/003-beat-bar-mapping/quickstart.md` end to end and fix steps that do not work as written
- [ ] T038 Developer: tap beats for all 5 songs with `poc record --tap-beats`, noting the time per song (SC-005, SC-009)
- [ ] T039 Developer: annotate beats by hand in 1–2 sections (about 8 bars each) with `poc annotate --beats`, starting with B・BLUE (SC-005)
- [ ] T040 Run `poc beats` (mix and drum_stem) and `poc evaluate-beats` for the 5 songs, `poc check-beats` on one song (SC-007), then `poc summarize-beats`
- [ ] T041 Write `docs/research/poc3-evaluation.md`: SC-001〜SC-009, per-song beat / downbeat F-measure for the raw / regularized / regularized + offset variants, BPM error, meter, mapping accuracy, tap jitter, mix vs drum stem, processing time / memory, limitations (rock only, 4/4 only, one tapper), and a Go/No-Go recommendation (no audio or song file paths)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup → Foundational**: 順番に
- **US1 (Phase 3)**: Foundational の後。MVP
- **US2 (Phase 4)**: US1 の後 (`BeatGrid` を使う)。US1 と同じ P1
- **US3 (Phase 5)**: US1・US2 の後 (評価で BeatGrid と対応付けを使う)。T026〜T028 (叩く録音) は US1 と並行して進めてよい
- **US4 (Phase 6)**: US3 の後
- **Polish (Phase 7)**: 全 User Story の後。T038 / T039 → T040 → T041

### Within User Story 1

- T012 → T013 → T014 → T015 → T016 → T017 (同じ `grid.py` / `run.py` を順に作る)
- テスト T008〜T011 は対応する実装の前に書き、失敗することを確認する

### Parallel Opportunities

- Setup: T002 は T001 と並行
- Foundational: T003 と T004 は並行。T005・T006 は `poc/beat/beats.py` を触るので順番に
- US1: T008〜T011 (テスト) は並行
- US2: T018・T019 は並行
- US3: T022〜T025 (テスト) は並行。T026〜T028 (録音) と T029〜T030 (手で付ける) は別ファイルで並行

---

## Implementation Strategy

### MVP First (User Story 1 + 2)

1. Phase 1・2 を終える (既存のテストが通ること)
2. US1: BeatGrid を作り、乱れが分かっている 3 曲で整理の効果を耳で確かめる (T017)。効果がなければ Human Review で整理の方式を見直す
3. US2: Reference Performance Data を作り、`poc bars` で小節ごとの打撃を確認する

### Incremental Delivery

1. US1 + US2 → 1 曲で `check.wav` と `poc bars` を確認
2. US3 → B・BLUE で拍を叩くパイロット (T028) → 評価が出ることを確認
3. US4 → 原曲と Drum Stem の比較
4. Polish → 5 曲の正解と評価 → Go/No-Go

---

## Notes

- 正解を作るとき (拍を叩く・手で付ける) は、推定した拍のクリックを聴かない・見ない (正解が推定に引っ張られるため)
- `poc record --click` (PoC 2) の動作は変えない。T005・T006・T012 で関数を移すときは、PoC 2 のテストで確認する
- コミットはタスクまたは論理的なまとまりごとに行う
