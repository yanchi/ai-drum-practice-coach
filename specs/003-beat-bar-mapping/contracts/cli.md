# Contract: CLI (PoC 3)

PoC 1・2 の `poc` コマンドにサブコマンドを追加する。終了コード (0 成功 / 1 失敗 / 2 入力の問題)、標準出力・標準エラー出力の使い分け、
`.partial` ディレクトリによる原子的な保存は PoC 1 ([contracts/cli.md](../../001-drum-stem-extraction/contracts/cli.md)) と同じ。

---

## `poc beats`

PoC 1 の run から拍と小節の頭を推定し、BeatGrid を作る (US1, US4)。

```text
uv run poc beats <poc1_run_dir> [--input {mix,drum_stem}] [--no-regularize] [--no-offset] [--output-dir output/beatgrids]
```

| 引数 | 既定値 | 説明 |
|---|---|---|
| `poc1_run_dir` | (必須) | PoC 1 の run ディレクトリ |
| `--input` | `mix` | `mix` = PoC 1 の入力曲 (原曲)、`drum_stem` = `drums.wav` |
| `--no-regularize` | off | 小節の頭を整理しない (推定そのままを使う) |
| `--no-offset` | off | ドラムへの位置合わせをしない。位置合わせには、この run の drum stem の最新の採譜結果 (PoC 2) が必要 |

**成功時**: `<output-dir>/<beatgrid_id>/` に次を作り、ディレクトリの絶対パスを標準出力に出す。標準エラー出力に BPM・拍子・補った拍の数・整理で変わった小節の頭の数・補正量を出す。

```text
beatgrid.json   # BeatGrid
check.wav       # 原曲 (−6 dB) + 拍のクリック (小節の頭 1600 Hz / ほか 1000 Hz)
```

**失敗時**: run ディレクトリが不正 (2)、位置合わせ用の採譜結果がない (2、`--no-offset` を案内)、推定中のエラー (1)。

## `poc map`

BeatGrid と打撃イベントから Reference Performance Data を作る (US2)。

```text
uv run poc map <beatgrid_dir> <transcription_dir> [--output-dir output/references]
uv run poc bars <reference_dir> <first_bar> [<last_bar>]
```

- `map`: `<output-dir>/<reference_id>/reference.json` を作り、パスを標準出力に出す。2 つの入力の `poc1_run_id` が違えば失敗 (2)。
- `bars`: 指定した小節の打撃を表で標準出力に出す (FR-009)。例:

  ```text
  bar beat grid  instrument  time_sec  deviation_ms
   12    1   0    kick        45.312      -4.0
   12    1   0    hihat       45.315      -1.0
   12    1   1/2  hihat       45.493      +2.5
  ```

## `poc record --tap-beats`

原曲を流しながら、TD-17 で拍を叩いて正解を作る (US3, FR-011 (1))。

```text
uv run poc record <poc1_run_dir> --tap-beats [--device "TD-17"] [--midi-port "TD-17"] [--output-dir output/recordings]
```

- カウントイン (4 回のクリック、120 BPM) のあと、**原曲**を流す。曲の拍のクリックは鳴らさない。
- 拍ごとにハイハット (手でもペダルでもよい)、小節の頭では同時にキック。
- `<output-dir>/<recording_id>/` に `recording.json` (`kind: "beat_taps"`)、`midi_notes.json`、`beat_groundtruth.json` (BeatGroundTruth) を作る。ドラムの音声は保存しない。
- 叩き損ねの疑いを標準エラー出力に時刻つきで出す。

## `poc annotate --beats`

手で拍と小節の頭を付ける (FR-011 (2))。PoC 2 の `poc annotate` の拡張。

```text
uv run poc annotate data/annotations/<名前>/annotation.yaml --beats
```

- `annotation.yaml` の `beat_regions` の区間を表示する。全体の波形のレーンをクリックで拍、Shift+クリックで小節の頭。
- 「保存」で `beats.csv` (`time_sec,label`、`b` / `d`) を `annotation.yaml` の隣に書く。

## `poc evaluate-beats`

BeatGrid を正解と比べる (US3, US4)。

```text
uv run poc evaluate-beats <beatgrid_dir> (--taps <recording_dir> | --annotation <annotation.yaml>) [--transcription <transcription_dir>] [--tolerance-ms 70] [--output-dir output/beat_evaluations]
```

- 推定そのまま・整理後・整理後 + 位置合わせの 3 通りを評価する (同じ推定から作り直す。モデルは再実行しない)。
- `--transcription` を付けると打撃の割り当て (FR-014) も評価する (既定: この run の drum stem の最新の採譜結果)。
- 同じ曲に `--annotation` の正解 (`beats.csv`) もあれば、叩いた正解のブレ (`tap_jitter_ms`) を併記する。
- `<output-dir>/<evaluation_id>/evaluation.json` を作り、要約を標準エラー出力に出す。

## `poc summarize-beats` / `poc check-beats`

```text
uv run poc summarize-beats [--evaluations-dir output/beat_evaluations] [--report-dir output/reports]
uv run poc check-beats <beatgrid_dir_a> <beatgrid_dir_b>
```

- `summarize-beats`: 曲ごとに最新の評価を集め、`output/reports/poc3_summary.md` / `.csv` に SC-001〜SC-009 の判定を出す。
- `check-beats`: 同じ入力の 2 つの BeatGrid の拍・小節の頭が一致するか (SC-007)。一致で 0、不一致で 1。
