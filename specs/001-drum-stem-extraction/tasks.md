---

description: "Task list for PoC 1: Drum Stem Extraction"
---

# Tasks: Drum Stem Extraction (PoC 1)

**Input**: Design documents from `/specs/001-drum-stem-extraction/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: 含める。plan.md / research.md R-14 でテスト方針を定めており、Constitution の Development Workflow が
「Lint / Test を通過してから Human Review」を求めているため。テストには合成信号のみを使い、著作物は使わない。

**Organization**: User Story ごとにフェーズを分け、各ストーリーを単独で実装・確認できるようにする。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 並行して実行できる (別ファイルで、未完了のタスクに依存しない)
- **[Story]**: 対応する User Story (US1〜US4)
- パスはリポジトリルートからの相対パス

## Path Conventions

- パッケージ: `poc/` (plan.md の Project Structure)
- テスト: `tests/unit/`, `tests/pipeline/`, `tests/integration/`
- 入力楽曲: `data/songs/`、出力: `output/runs/`, `output/reports/` (どちらも `.gitignore` 済み)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Python プロジェクトの初期化と開発ツール

- [ ] T001 Create `pyproject.toml` at repository root: project name `ai-drum-practice-coach-poc`, `requires-python = ">=3.11,<3.12"`, dependencies `demucs==4.1.0`, `numpy`, `soundfile`, `pyyaml`, `julius` (pyyaml / julius are imported directly, so declare them), dev dependency group with `pytest` and `ruff`, `[project.scripts] poc = "poc.cli:main"`, build backend `hatchling` with `packages = ["poc"]`, `[tool.ruff]` (line-length 100, target py311, lint rules `E,F,I,UP,B`), `[tool.pytest.ini_options]` (`testpaths = ["tests"]`, marker `slow: runs the real Demucs model`, `addopts = "-m 'not slow'"`); also create `.python-version` containing `3.11`
- [ ] T002 Create package skeleton with empty `__init__.py` files: `poc/__init__.py`, `poc/audio/__init__.py`, `poc/separation/__init__.py`, `poc/evaluation/__init__.py`; create test directories `tests/unit/`, `tests/pipeline/`, `tests/integration/` (no `__init__.py`; keep existing `.gitkeep` files in `poc/transcription/`, `poc/beat/`, `poc/fixtures/`)
- [ ] T003 Install ffmpeg with `brew install ffmpeg`, verify `ffmpeg -version` and `ffprobe -version`, then run `uv sync` to create `.venv` and `uv.lock` (commit `uv.lock`; `.venv/` is already in `.gitignore`)
- [ ] T004 [P] Create `tests/conftest.py` with helpers that generate synthetic audio only: `sine(freq, sec, sr, channels)`, `click_track(bpm, sec, sr, channels)` returning `numpy.float32` arrays shaped `(channels, samples)`, `write_wav(tmp_path, name, audio, sr, subtype)` using soundfile, and a `FakeSeparator` fixture (returns the input mix as `drums` and zeros as `accompaniment`, reports `model_samplerate=44100`)

**Checkpoint**: `uv run ruff check .` と `uv run pytest` (0 tests) が通る

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: すべての User Story が使う Domain Model・エラー・Separator の境界・CLI の骨格

**⚠️ CRITICAL**: このフェーズが終わるまで User Story の作業を始めない

- [ ] T005 [P] Create `poc/errors.py` with exception hierarchy: `PocError` (base, `exit_code = 1`), `UserInputError(PocError)` (`exit_code = 2`), `DrmProtectedError(UserInputError)`, `UnsupportedAudioError(UserInputError)`, `InputReadError(UserInputError)`, `FfmpegNotFoundError(PocError)`, `SeparationError(PocError)`; error messages follow the table in `specs/001-drum-stem-extraction/contracts/cli.md`
- [ ] T006 [P] Create `poc/domain.py` with frozen dataclasses from `data-model.md`: `Song`, `Stem`, `SeparatorInfo`, `AlignmentCheck`, `RunWarning` (fields `code`, `message`, `value`, `threshold`), `SeparationRun` (fields `timings_sec`, `peak_memory`, `environment` default to `None` so US1 can write a run without US3), plus `to_dict()` helpers producing the JSON shape in `contracts/files.md` (`schema_version: 1`, paths as strings); no Demucs or torch imports in this module
- [ ] T007 [P] Create `poc/separation/base.py` with `SeparationOutput` dataclass (`drums: np.ndarray`, `accompaniment: np.ndarray`, both `(channels, samples)` float32 at the input sample rate and length; `info: SeparatorInfo`) and a `Separator` `typing.Protocol` with `separate(audio: np.ndarray, sample_rate: int) -> SeparationOutput`
- [ ] T008 Create `poc/cli.py` skeleton: `argparse` parser with subcommands `separate`, `summarize`, `check-repro` (arguments exactly as `contracts/cli.md`, handlers raise `NotImplementedError` for now), `main(argv=None) -> int` that catches `PocError` and prints `error: <message>` to stderr and returns `exc.exit_code`

**Checkpoint**: `uv run poc --help` が 3 つのサブコマンドを表示する

---

## Phase 3: User Story 1 - 1 曲からドラムだけの音源を得る (Priority: P1) 🎯 MVP

**Goal**: ユーザー所有の楽曲 1 曲から、原曲と同じ SR・チャンネル数・サンプル数で時間ずれのない Drum Stem (32-bit float WAV) を作る。DRM 保護ファイルは拒否する

**Independent Test**: `uv run poc separate data/songs/<曲>` で `output/runs/<run_id>/drums.wav` と `run.json` ができ、`run.json` の `alignment.passed` が `true`。再生してドラムが聴こえる。`.m4p` を渡すと終了コード 2 で拒否される

### Tests for User Story 1

- [ ] T009 [P] [US1] Write `tests/unit/test_probe.py`: DRM detection for `.m4p` extension, for `codec_tag_string == "drms"`, and for ffprobe stderr containing `drm`/`encrypted`/`protected` (all raise `DrmProtectedError`); unsupported codec (e.g. `opus`) and 3+ channels raise `UnsupportedAudioError`; supported codecs `pcm_s16le`, `pcm_s24be`, `pcm_f32le`, `mp3`, `aac`, `alac` pass; use hand-written ffprobe JSON dicts (no real protected files)
- [ ] T010 [P] [US1] Write `tests/unit/test_signal.py`: `resample` 48000→44100→48000 round trip of a click track keeps clicks within ±1 sample; `fit_length` pads/truncates to exact length; `match_channels` stereo→mono averages and mono→stereo duplicates; `peak` and `rms_db_relative`; `estimate_lag` detects a known 10-sample and −10-sample shift and returns 0 for identical signals; window selection picks the loudest 30 s region (use a 60 s signal with a loud second half)
- [ ] T011 [P] [US1] Write `tests/unit/test_decode.py`: decode WAV files (mono 48 kHz, stereo 44.1 kHz) written by `write_wav` and check shape, dtype float32, sample rate, sample count and sha256; skip with `pytest.mark.skipif` when `ffmpeg` is not on PATH
- [ ] T012 [P] [US1] Write `tests/pipeline/test_run_us1.py` using `FakeSeparator`: successful run creates `<output>/<run_id>/drums.wav` with the same SR / channels / samples as the input and a `run.json` whose `alignment.passed` is true; run_id matches `^\d{8}-\d{6}_[0-9a-f]{8}$`; a separator that raises leaves no `<run_id>` or `.partial` directory; drums 40 dB quieter than the mix produce warning `drums_nearly_silent`; drums with peak 1.5 produce `clipping_risk` and are written unclipped
- [ ] T013 [P] [US1] Write `tests/integration/test_demucs.py` marked `@pytest.mark.slow`: run `DemucsSeparator(device="cpu")` on a 10 s synthetic click track at 48 kHz stereo; assert output shapes equal input shape and `estimate_lag` between `drums + accompaniment` and input is within ±1 ms

### Implementation for User Story 1

- [ ] T014 [P] [US1] Implement `poc/audio/probe.py`: `probe(path) -> ProbeResult` running `ffprobe -v error -print_format json -show_format -show_streams <path>` via `subprocess.run` (raise `FfmpegNotFoundError` if the binary is missing, `InputReadError` on missing/unreadable files), selecting the first audio stream; `check_drm(path, probe_json, stderr)` and `check_supported(probe_json)` per research R-05 and data-model `Song` validation (supported: `pcm_*`, `mp3`, `aac`, `alac`; channels 1–2)
- [ ] T015 [P] [US1] Implement `poc/audio/decode.py`: `load_song(path) -> tuple[Song, np.ndarray, list[RunWarning]]` that calls `probe`, computes sha256 of the file bytes, decodes with `ffmpeg -v error -i <path> -map 0:a:0 -f f32le -acodec pcm_f32le -ac <channels> -ar <sample_rate> pipe:1`, reshapes to `(channels, samples)`, and adds warning `duration_mismatch` when decoded duration differs from ffprobe `format.duration` by more than 1 ms (research R-04)
- [ ] T016 [P] [US1] Implement `poc/audio/signal.py`: `resample(audio, from_sr, to_sr)` using `julius.resample_frac` on a torch tensor, `fit_length(audio, n)`, `match_channels(audio, channels)`, `peak(audio)`, `rms_db_relative(stem, mix)`, `loudest_window_start(mono, sr, sec=30)`, and `estimate_lag(reference, target, sr, window_sec=30) -> (lag_samples, window_start_sec)` using FFT cross-correlation on mono signals (research R-06, R-07)
- [ ] T017 [US1] Implement `poc/separation/demucs_adapter.py`: `DemucsSeparator(model="htdemucs", device="auto", seed=0)` implementing `Separator`; resolve `auto` to `mps` if `torch.backends.mps.is_available()` else `cpu`; seed `random`, `numpy`, `torch`; build `demucs.api.Separator(model=..., device=..., shifts=0, split=True, overlap=0.25, progress=False)`; in `separate`, convert to stereo, resample to `model.samplerate` if needed, call `separate_tensor`, take `drums` and sum of all other sources as accompaniment, resample back, `fit_length` to input length and `match_channels` to input channels; wrap exceptions (including MPS/CPU out-of-memory) in `SeparationError` suggesting `--device cpu`; fill `SeparatorInfo` (version via `importlib.metadata.version("demucs")`)
- [ ] T018 [US1] Implement `poc/evaluation/run.py`: `run_separation(audio_path, output_dir, separator, *, write_accompaniment) -> Path` that loads the song, separates, runs the alignment check on `drums + accompaniment` vs the mix (`AlignmentCheck.passed = abs(lag_ms) <= 1.0 and length_match`, warning `alignment_failed` otherwise), adds `drums_nearly_silent` (threshold −30 dB) and `clipping_risk` (peak > 1.0) warnings, writes `drums.wav` with `soundfile.write(..., subtype="FLOAT")` and `run.json` into `<output_dir>/<run_id>.partial/`, renames to `<run_id>/` on success and removes the `.partial` directory on any exception (research R-08, R-10, R-12); create `output_dir` if missing
- [ ] T019 [US1] Wire `separate` in `poc/cli.py`: build `DemucsSeparator(device=args.device, seed=args.seed)`, call `run_separation`, print the absolute run directory to stdout and each warning as `warning: <code>: <message>` to stderr (contracts/cli.md)
- [ ] T020 [US1] Manually verify with one user-owned song in `data/songs/`: run `uv run poc separate`, listen to `drums.wav`, play it against the original in a DAW, and confirm `run.json` `alignment.passed` is true (quickstart.md §4)

**Checkpoint**: US1 単独で Drum Stem が得られる (MVP)

---

## Phase 4: User Story 2 - 分離品質を測定して記録する (Priority: P2)

**Goal**: 実行ごとに評価シート (YAML) のテンプレートを出し、記入済みシートを集計して SC-001〜SC-005 を判定する

**Independent Test**: 1 曲分の `evaluation.yaml` を記入して `uv run poc summarize` を実行すると、`output/reports/summary.csv` と `summary.md` ができ、確認率と聴感評価の平均が表示される

### Tests for User Story 2

- [ ] T021 [P] [US2] Write `tests/unit/test_sheet.py`: generated template text matches the YAML in `contracts/files.md` for a given run_id and loads back with all `null` values; a sheet with any `null` is reported as incomplete; validation errors (include file name and field) for `drum_clarity: 6`, `detected > original`, negative counts, `end_sec <= start_sec`, not exactly 3 sections, duplicate labels, unsupported `schema_version`
- [ ] T022 [P] [US2] Write `tests/unit/test_summary.py`: hit rate per section, per instrument and per song (Σdetected/Σoriginal); means of `drum_clarity` / `bleed` / `artifacts`; SC-001 needs ≥5 evaluated songs (otherwise status `INSUFFICIENT`); SC-002 ≥ 0.90; SC-003 clarity ≥ 4.0 and bleed ≥ 3.0; SC-004 uses `run.json` `alignment.lag_ms` (all ≤ 1 ms); SC-005 normalizes `timings_sec.total / duration_sec * 240` and reports `N/A` when `timings_sec` is missing; SC-007 flags runs missing required `run.json` keys

### Implementation for User Story 2

- [ ] T023 [P] [US2] Add `ListeningRating`, `CheckSection`, `SeparationEvaluation` dataclasses to `poc/domain.py` (data-model.md)
- [ ] T024 [US2] Implement `poc/evaluation/sheet.py`: `render_template(run_id) -> str` producing exactly the template in `contracts/files.md` (including the instruction comments), `load_sheet(path) -> SeparationEvaluation | None` (None when incomplete) and validation raising `SheetValidationError(UserInputError)` with file and field names
- [ ] T025 [US2] Update `poc/evaluation/run.py` to write `evaluation.yaml` (from `render_template`) into the run directory before the rename
- [ ] T026 [US2] Implement `poc/evaluation/summary.py`: scan `<runs_dir>/*/run.json` and `evaluation.yaml`, skip incomplete sheets (list their run_ids on stderr), compute per-song rows and SC-001〜SC-005 / SC-007 statuses (`PASS` / `FAIL` / `INSUFFICIENT` / `N/A`), write `summary.csv` (columns from data-model.md `EvaluationSummary`) and `summary.md` (format in `contracts/files.md`); raise `UserInputError` when no completed sheet exists
- [ ] T027 [US2] Wire `summarize` in `poc/cli.py` (`--runs-dir`, `--report-dir`), printing `summary.md` to stdout

**Checkpoint**: US1 + US2 で、分離から評価・集計まで一通りできる

---

## Phase 5: User Story 3 - 実行条件を再現・比較できるよう記録する (Priority: P3)

**Goal**: 処理時間・最大メモリ・環境を `run.json` に記録し、同じ入力の 2 回の実行を比較できるようにする

**Independent Test**: 同じ曲を 2 回 `poc separate` し、`run.json` に `timings_sec` / `peak_memory` / `environment` が入っていること、`uv run poc check-repro <a> <b>` が `result=PASS` を出すことを確認する

### Tests for User Story 3

- [ ] T028 [P] [US3] Write `tests/unit/test_metrics.py`: `Stopwatch` records named stages and a `total`; `peak_rss_bytes()` returns a positive int (macOS reports bytes); `environment_info()` contains `python`, `torch`, `demucs`, `ffmpeg`, `platform`, `machine` keys (ffmpeg value may be `"not found"` when missing)
- [ ] T029 [P] [US3] Write `tests/unit/test_repro.py`: identical drums.wav → `max_abs_diff == 0` and PASS; added noise of 1e-3 → FAIL with tolerance 1e-4; different `song.sha256` or different `separator.params` → `UserInputError` (exit 2); differing only in `separator.device` is allowed
- [ ] T030 [P] [US3] Extend `tests/pipeline/test_run_us3.py` using `FakeSeparator`: `run.json` contains `timings_sec` with `decode` / `separate` / `write` / `total`, `peak_memory.rss_bytes`, `environment`, and `separator.params.seed`

### Implementation for User Story 3

- [ ] T031 [P] [US3] Implement `poc/evaluation/metrics.py`: `Stopwatch` context manager per stage using `time.perf_counter`, `peak_rss_bytes()` via `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss` (bytes on macOS, ×1024 on Linux), `mps_driver_bytes()` returning `torch.mps.driver_allocated_memory()` when MPS is in use else `None`, and `environment_info()` (Python / torch / demucs versions via `importlib.metadata`, first line of `ffmpeg -version`, `platform.platform()`, CPU name via `sysctl -n machdep.cpu.brand_string` on macOS) (research R-11)
- [ ] T032 [US3] Update `poc/evaluation/run.py` to measure `decode` / `separate` / `write` stages, track the peak MPS driver memory after separation, and fill `timings_sec`, `peak_memory`, `environment` in `run.json`
- [ ] T033 [US3] Implement `poc/evaluation/repro.py`: `compare_runs(run_a, run_b, tolerance=1e-4) -> (max_abs_diff, passed)` that checks `song.sha256` and `separator` (excluding `device`) match, then compares `drums.wav` sample-wise; wire `check-repro` in `poc/cli.py` printing `max_abs_diff=<v> tolerance=<t> result=PASS|FAIL` and returning 0 / 1 (contracts/cli.md)
- [ ] T034 [US3] Manually verify: separate the same user-owned song twice and run `uv run poc check-repro` (quickstart.md §6)

**Checkpoint**: 各実行の条件と処理コストが記録され、再現性を確認できる

---

## Phase 6: User Story 4 - ドラム抜き音源も得る (Priority: P4)

**Goal**: Drum Stem と同時に Accompaniment Stem (bass + other + vocals) を保存する

**Independent Test**: `poc separate` 後に `accompaniment.wav` があり、原曲と同じ長さで再生できる。`--no-accompaniment` では作られない

- [ ] T035 [P] [US4] Write `tests/pipeline/test_run_us4.py` using `FakeSeparator`: default run writes `accompaniment.wav` (same SR / channels / samples as input, listed in `run.json` `stems` with `kind: accompaniment`); `write_accompaniment=False` writes no file and lists only drums
- [ ] T036 [US4] Update `poc/evaluation/run.py` to write `accompaniment.wav` (32-bit float) and its `Stem` record when `write_accompaniment` is true, and wire `--no-accompaniment` in `poc/cli.py` (alignment check still uses drums + accompaniment in memory)

**Checkpoint**: すべての User Story が単独で動作する

---

## Phase 7: Polish & Evaluation

**Purpose**: 全体の品質確認と、PoC 1 の Go/No-Go 判断の材料作り

- [ ] T037 [P] Update `README.md` with a short "PoC 1: Drum Stem Extraction" section linking to `specs/001-drum-stem-extraction/quickstart.md` (setup, `poc separate`, `poc summarize`)
- [ ] T038 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`, and `uv run pytest -m slow`; fix all failures
- [ ] T039 Follow `specs/001-drum-stem-extraction/quickstart.md` end to end on a clean `uv sync` and fix any step that does not work as written
- [ ] T040 Evaluate at least 5 user-owned songs of different genres (separate, fill `evaluation.yaml`, run `check-repro` on one song, run `poc summarize`) — performed by the developer
- [ ] T041 Write `docs/research/poc1-evaluation.md` from `output/reports/summary.md` and the `check-repro` result: SC-001〜SC-007 results, per-instrument hit rates (especially HiHat, risk R3), processing time and memory on the M1, warnings observed, ghost note notes, and a Go/No-Go recommendation for Human Review (do not include audio or song file paths)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 依存なし
- **Foundational (Phase 2)**: Setup 完了後。すべての User Story をブロックする
- **US1 (Phase 3)**: Foundational 完了後。MVP
- **US2 (Phase 4)**: US1 完了後 (`run.py` と run ディレクトリに評価シートを追加するため)
- **US3 (Phase 5)**: US1 完了後。US2 とは独立 (どちらも `run.py` を編集するため、同時に進める場合は T025 と T032 の競合に注意)
- **US4 (Phase 6)**: US1 完了後。US2 / US3 とは独立
- **Polish (Phase 7)**: 全 User Story 完了後。T040 → T041 の順

### User Story Dependencies

- **US1 (P1)**: Foundational のみに依存
- **US2 (P2)**: US1 の run ディレクトリと `run.json` (`alignment`) に依存。`timings_sec` がない場合 SC-005 は `N/A` になるので US3 には依存しない
- **US3 (P3)**: US1 の `run.py` に依存
- **US4 (P4)**: US1 の `run.py` と adapter の `accompaniment` 出力に依存

### Within Each User Story

- テストを先に書き、失敗することを確認してから実装する
- Domain Model → 処理 (audio / separation / evaluation) → CLI の順
- 手動確認タスク (T020, T034) はそのストーリーの最後

### Parallel Opportunities

- Phase 1: T004 は T001〜T003 と並行可能
- Phase 2: T005 / T006 / T007 は並行可能 (T008 は T005 の後)
- US1: テスト T009〜T013 は並行可能。実装 T014 / T015 / T016 は並行可能 (T015 は T014 の関数を呼ぶが、インターフェースは本ファイルで定義済み)。T017 → T018 → T019 は順番に
- US2: T021 / T022 / T023 は並行可能
- US3: T028 / T029 / T030 / T031 は並行可能
- US2 と US3 と US4 は、US1 完了後に別々に進められる (`run.py` の編集だけ順番に行う)

---

## Parallel Example: User Story 1

```bash
# US1 のテストをまとめて書く:
Task: "T009 Write tests/unit/test_probe.py"
Task: "T010 Write tests/unit/test_signal.py"
Task: "T011 Write tests/unit/test_decode.py"
Task: "T012 Write tests/pipeline/test_run_us1.py"
Task: "T013 Write tests/integration/test_demucs.py"

# 独立したモジュールを並行して実装する:
Task: "T014 Implement poc/audio/probe.py"
Task: "T015 Implement poc/audio/decode.py"
Task: "T016 Implement poc/audio/signal.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Setup
2. Phase 2: Foundational
3. Phase 3: US1
4. **止めて確認**: 1 曲で Drum Stem を聴き、`alignment.passed` を確認する。この時点で分離品質が明らかに足りなければ、評価の仕組みを作る前に Human Review で方式を見直す

### Incremental Delivery

1. Setup + Foundational → 骨格
2. US1 → Drum Stem が得られる (MVP)
3. US2 → 評価と集計ができる
4. US3 → 処理コストと再現性が記録される
5. US4 → 伴奏も得られる
6. Polish → 5 曲以上で評価し、Go/No-Go の Human Review へ

---

## Notes

- [P] は別ファイルで、未完了タスクに依存しないもの
- 楽曲・stem・`run.json` はコミットしない (`data/`, `output/` は `.gitignore` 済み)
- 新しい依存を追加する場合は Human Review を受ける (Constitution の Review Gates)
- 各タスクまたは論理的なまとまりごとにコミットする
