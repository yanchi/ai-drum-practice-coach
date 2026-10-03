# Data Model: Drum Stem Extraction (PoC 1)

**Date**: 2026-10-03
**Source**: [spec.md](spec.md) Key Entities, [research.md](research.md)

Domain Model は `poc/domain.py` に dataclass として定義する。Demucs のテンソルや stem 名は adapter (`poc/separation/`) の中だけで扱い、ここには出さない (Constitution III)。

---

## Song

ユーザー所有の入力楽曲。

| Field | Type | Rule |
|---|---|---|
| `path` | Path | 存在するファイル。リポジトリ外 (`data/` 等) を推奨 |
| `sha256` | str | ファイル内容の SHA-256 (16 進 64 文字)。入力の識別子 |
| `format` | str | ffprobe の `format_name` (例: `mp3`, `mov,mp4,m4a,...`, `wav`, `aiff`) |
| `codec` | str | オーディオストリームの `codec_name` (例: `mp3`, `aac`, `alac`, `pcm_s16le`) |
| `sample_rate` | int | > 0 |
| `channels` | int | 1 または 2 (3 以上は `UnsupportedAudioError`) |
| `num_samples` | int | デコード後のサンプル数 (チャンネルあたり) |
| `duration_sec` | float | `num_samples / sample_rate` |

**Validation**:
- 対応形式は WAV / AIFF / MP3 / AAC / ALAC。それ以外の `codec_name` は `UnsupportedAudioError`
- DRM 判定 (research R-05) に当てはまるものは `DrmProtectedError`。Song は作らない
- `num_samples / sample_rate` と ffprobe の duration の差が 1 ms を超えたら、警告 `duration_mismatch`

## Stem

分離された音声 1 本。Drum Stem / Accompaniment Stem の共通型。

| Field | Type | Rule |
|---|---|---|
| `kind` | `"drums"` \| `"accompaniment"` | |
| `path` | Path | run ディレクトリ内の WAV (32-bit float) |
| `sample_rate` | int | Song.sample_rate と同じ |
| `channels` | int | Song.channels と同じ (モノラルの曲ならステレオ出力をモノラルにまとめる) |
| `num_samples` | int | Song.num_samples と同じ |
| `peak` | float | 絶対値の最大。> 1.0 なら警告 `clipping_risk` |
| `rms_db_relative_to_mix` | float | 原曲の RMS に対する dB。drums で < -30 dB なら警告 `drums_nearly_silent` |

## SeparationRun (実行記録)

1 回の分離実行。`run.json` として保存する。

| Field | Type | Rule |
|---|---|---|
| `run_id` | str | `<YYYYMMDD-HHMMSS>_<sha256 先頭 8 文字>` |
| `created_at` | str | ISO 8601 (タイムゾーン付き) |
| `status` | `"succeeded"` \| `"failed"` | `failed` の場合 run ディレクトリは残さず、エラーを標準エラー出力に出す |
| `song` | Song | |
| `separator` | SeparatorInfo | |
| `stems` | Stem[] | drums は必須、accompaniment は任意 |
| `alignment` | AlignmentCheck | |
| `timings_sec` | dict | `decode` / `separate` / `write` / `total` |
| `peak_memory` | dict | `rss_bytes` (必須)、`mps_driver_bytes` (MPS 使用時のみ) |
| `environment` | dict | `python` / `torch` / `demucs` / `ffmpeg` / `platform` / `machine` |
| `warnings` | Warning[] | |

**State transitions**: `(running: <run_id>.partial/)` → `succeeded: <run_id>/` へリネーム。失敗したら `.partial` を削除する。`failed` の記録は残さない (FR-014)。

### SeparatorInfo

| Field | Type | Rule |
|---|---|---|
| `method` | str | 例: `demucs` |
| `version` | str | パッケージのバージョン (例: `4.1.0`) |
| `model` | str | 例: `htdemucs` |
| `params` | dict | `shifts` (= 0)、`overlap`、`segment`、`split`、`seed` |
| `device` | str | `mps` / `cpu` |
| `model_samplerate` | int | 例: 44100 |

### AlignmentCheck (SC-004)

| Field | Type | Rule |
|---|---|---|
| `method` | str | `stem_sum_xcorr` |
| `window_start_sec` | float | 相互相関に使った 30 秒区間の開始 |
| `lag_samples` | int | 全 stem の和の、原曲に対する遅れ (正 = stem が遅い) |
| `lag_ms` | float | `lag_samples / sample_rate * 1000` |
| `length_match` | bool | すべての stem の `num_samples` が Song と一致 |
| `passed` | bool | `abs(lag_ms) <= 1.0` かつ `length_match` |

### Warning

| Field | Type | Rule |
|---|---|---|
| `code` | str | `drums_nearly_silent` / `clipping_risk` / `duration_mismatch` / `alignment_failed` |
| `message` | str | 人が読める説明 |
| `value` | float \| null | 判定に使った値 |
| `threshold` | float \| null | 判定に使った閾値 |

## SeparationEvaluation (評価結果)

開発者が記入する評価シート。`output/runs/<run_id>/evaluation.yaml`。テンプレートはコマンドで生成する。

| Field | Type | Rule |
|---|---|---|
| `run_id` | str | 対応する SeparationRun |
| `song_label` | str | 開発者が付ける曲名ラベル (集計表で使う。ファイル名とは別) |
| `genre` | str | 評価セットのジャンルの偏りを確認するため |
| `evaluated_at` | str | 日付 (YYYY-MM-DD) |
| `listening` | ListeningRating | |
| `sections` | CheckSection[3] | ちょうど 3 個 |
| `notes` | str | 任意 |

### ListeningRating (FR-009, SC-003)

| Field | Type | Rule |
|---|---|---|
| `drum_clarity` | int | 1–5 (5 = ドラムがはっきり聴き取れる) |
| `bleed` | int | 1–5 (5 = 他の楽器の混入なし) |
| `artifacts` | int | 1–5 (5 = 音質の劣化なし)。記録のみで合否には使わない |

### CheckSection (FR-008, SC-002)

| Field | Type | Rule |
|---|---|---|
| `label` | `"verse"` \| `"chorus"` \| `"fill"` | 3 区間で重複しない |
| `start_sec` | float | 原曲内の開始時刻 (0 以上、曲長未満) |
| `end_sec` | float | > `start_sec`。4 小節分 |
| `counts` | dict | `kick` / `snare` / `hihat` それぞれ `{original: int, detected: int}`。`0 <= detected <= original` |
| `ghost_notes_memo` | str | 任意。ゴーストノートが残っていたか・消えていたか |

**派生値**: 区間の確認率 = Σdetected / Σoriginal。曲の確認率 = 3 区間の Σdetected / Σoriginal。楽器別の確認率も同様に計算する。

## EvaluationSummary (FR-011)

集計コマンドの出力。評価シートが記入済み (`listening` と `sections` がすべて埋まっている) の run だけを対象にする。

- `output/reports/summary.csv`: 1 行 1 曲。`run_id`, `song_label`, `genre`, `drum_clarity`, `bleed`, `artifacts`, `hit_rate`, `hit_rate_kick`, `hit_rate_snare`, `hit_rate_hihat`, `alignment_lag_ms`, `total_sec`, `peak_rss_mb`, `device`
- `output/reports/summary.md`: 全体の平均と、SC-001〜SC-005 の判定 (PASS / FAIL / 曲数不足)

## Relationships

```text
Song 1 ── * SeparationRun 1 ── 1..2 Stem
                    │
                    └── 0..1 SeparationEvaluation ── 3 CheckSection

EvaluationSummary ── * SeparationEvaluation (記入済みのもの)
```

同じ Song を別の設定・別の方式で分離した場合は SeparationRun が増える。分離方式を追加して比較するときは、同じ Song に同じ `sections` (開始・終了時刻) を使う (spec Assumptions)。
