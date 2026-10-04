# Data Model: Beat / Downbeat Analysis and Bar Mapping (PoC 3)

`poc/domain.py` に追加する。ML ライブラリに依存しない (Constitution III)。時刻はすべて原曲の時間軸 (秒)。
JSON には `schema_version: 1` を付ける (PoC 1・2 と同じ)。

## Beat

| フィールド | 型 | 説明 |
|---|---|---|
| `time_sec` | float | 拍の時刻 (位置合わせ後) |
| `inferred` | bool | 推定で取りこぼされ、前後の間隔から補った拍 (R-02) |
| `downbeat_activation` | float \| null | 小節の頭らしさ (0〜1)。補った拍は null |

## BeatGrid

| フィールド | 型 | 説明 |
|---|---|---|
| `beatgrid_id` | str | `<日時>_<input>_<音声ハッシュ先頭8桁>` |
| `created_at` | str | ISO 8601 |
| `input` | object | `kind` (`mix` / `drum_stem`)、`poc1_run_id`、`audio_sha256`、`duration_sec` |
| `estimator` | object | `method` (`beat_this`)、`version`、`checkpoint`、`device` |
| `beats` | Beat[] | 時刻順 |
| `downbeats` | float[] | 対応付けに使う小節の頭 (整理後。整理しない設定なら推定そのまま) |
| `downbeats_raw` | float[] | 推定そのままの小節の頭 (位置合わせ後) |
| `downbeat_source` | `"regularized"` \| `"raw"` | `downbeats` の出どころ |
| `meter` | int | 1 小節の拍数 (推定そのままの小節の頭の間の拍数の最頻値) |
| `bpm` | float | 曲全体の BPM (拍の間隔の中央値から) |
| `bpm_sections` | {start_sec, end_sec, bpm}[] | 16 小節ごとの BPM |
| `offset` | object | `applied_ms` (グリッド全体をずらした量、負 = 早める)、`from_transcription_id` (null = 補正なし) |
| `regularization` | object | `applied` (bool)、`phase_changes` (位相が飛んだ拍の時刻の一覧)、`changed_downbeats` (推定そのままと違う小節の頭の数) |
| `gaps` | {start_sec, end_sec}[] | 補えなかった拍のない区間 (R-05 の 5) |
| `warnings` | RunWarning[] | 例: 拍子が 4 以外で整理しなかった |
| `timings_sec`, `peak_memory`, `environment` | | PoC 1・2 と同じ |

**検証**: `beats` は時刻が厳密に増加する。`downbeats` ⊆ `beats` の時刻。`meter` ≥ 1。

## BeatPosition

| フィールド | 型 | 説明 |
|---|---|---|
| `bar` | int \| null | 小節番号 (1 始まり。最初の小節の頭より前は 0。拍のない区間は null) |
| `beat` | int \| null | 小節内の拍番号 (1 始まり) |
| `position` | float \| null | 連続した拍の位置 x の小数部分 (0 ≤ position < 1、丸める前) |
| `grid` | str \| null | 一番近いグリッド位置: `"0"`, `"1/4"`, `"1/3"`, `"1/2"`, `"2/3"`, `"3/4"` |
| `deviation_ms` | float \| null | グリッド位置の時刻との差 (負 = 早い) |
| `unmapped_reason` | str \| null | 例: `"no_beats"` (拍のない区間)、`"before_first_beat"` |

## ReferencePerformance

| フィールド | 型 | 説明 |
|---|---|---|
| `reference_id` | str | `<日時>_<beatgrid_id の末尾>` |
| `created_at` | str | |
| `beatgrid_id` | str | 使った BeatGrid |
| `transcription_id` | str | 使った打撃イベントの抽出 (PoC 2) |
| `poc1_run_id` | str | 両者で一致していること (一致しなければ作らない) |
| `events` | {event: DrumEvent, position: BeatPosition}[] | 時刻順。Tom・Cymbal も含む |
| `bars` | int | 小節の数 |
| `unmapped_count` | int | 小節・拍を付けられなかった打撃の数 |

ファイルには BeatGrid を埋め込まず ID だけ持つ。小節の範囲での取り出し (FR-009) は `bar` で絞り込む。

## BeatGroundTruth

| フィールド | 型 | 説明 |
|---|---|---|
| `source` | `"td17_taps"` \| `"manual"` | 叩いた (R-06) / 手で付けた (R-07) |
| `poc1_run_id` | str | |
| `regions` | [start, end][] | 対象区間。叩いた場合は最初と最後の拍の間 1 つ |
| `beats` | float[] | 拍の時刻 |
| `downbeats` | float[] | 小節の頭の時刻 (⊆ beats) |
| `alignment` | object \| null | 叩いた場合: `calibration_id`、パッドごとのずれ (PoC 2 の MidiAudioAlignment と同じ形) |
| `warnings` | RunWarning[] | 叩き損ねの疑い (R-06) |

## BeatEvaluation

| フィールド | 型 | 説明 |
|---|---|---|
| `evaluation_id` | str | |
| `beatgrid_id` | str | |
| `groundtruth` | object | `source`、`recording_id` または `annotation`、`regions` |
| `tolerance_ms` | float | 既定 70 |
| `variants` | {name, beats: Metrics, downbeats: Metrics, bpm_error_pct, meter_match, mapping}[] | `name` は `raw` (推定そのまま・位置合わせなし)、`regularized`、`regularized_offset` (採用する形) |
| `mapping` | object | `events` (対象の打撃数)、`matched_bar`、`matched_beat`、`matched_grid`、`accuracy` (3 つがそろった割合) |
| `tap_jitter_ms` | object \| null | 同じ曲の手で付けた正解があれば: `median_abs`、`p95_abs`、`count` |

`Metrics` = `tp`、`fp`、`fn`、`precision`、`recall`、`f_measure`、`timing_ms` (`median_abs`, `p95_abs`, `median_signed`)。

## 関係

```text
SeparationRun (PoC 1) ─┬─> BeatGrid ──────────────┐
                       ├─> TranscriptionRun (PoC 2)┴─> ReferencePerformance
                       └─> BeatGroundTruth (taps / manual)
BeatGrid + BeatGroundTruth (+ TranscriptionRun) ──> BeatEvaluation
```
