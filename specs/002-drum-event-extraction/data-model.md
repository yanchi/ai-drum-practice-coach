# Data Model: Drum Event Extraction (PoC 2)

**Date**: 2026-10-04
**Source**: [spec.md](spec.md) Key Entities, [research.md](research.md)

`poc/domain.py` に dataclass として追加する。ADTOF のクラス番号・活性値・TD-17 のノート番号は adapter の中だけで扱い、ここには出さない (Constitution III)。

---

## DrumEvent

| Field | Type | Rule |
|---|---|---|
| `time_sec` | float | ≥ 0。音声の先頭からの秒数 |
| `instrument` | `"kick"` \| `"snare"` \| `"hihat"` \| `"tom"` \| `"cymbal"` | |
| `strength` | float | 0〜1 |

同じ `time_sec` に別の `instrument` のイベントが並んでよい (FR-003)。同じ楽器のイベントは時刻順で、20 ms 以内に重ならない (ピーク検出の仕様)。

## TranscriptionRun (抽出の実行記録)

`output/transcriptions/<transcription_id>/transcription.json`。

| Field | Type | Rule |
|---|---|---|
| `schema_version` | int | 1 |
| `transcription_id` | str | `<YYYYMMDD-HHMMSS>_<入力音声の sha256 先頭 8 文字>` |
| `created_at` | str | ISO 8601 |
| `input` | TranscriptionInput | |
| `transcriber` | TranscriberInfo | |
| `events` | DrumEvent[] | 時刻順 |
| `event_counts` | dict | 楽器ごとの数 |
| `timings_sec` | dict | `load` / `infer` / `pick` / `write` / `total` |
| `peak_memory` | dict | `rss_bytes` |
| `environment` | dict | PoC 1 と同じ項目 + `adtof_pytorch` (コミット) |
| `warnings` | RunWarning[] | 例: `no_events` (イベントが 0 件) |

### TranscriptionInput

| Field | Type | Rule |
|---|---|---|
| `kind` | `"drum_stem"` \| `"mix"` \| `"accompaniment"` | `mix` = 分離前の音声 (US3)、`accompaniment` = 伴奏だけ (FR-015) |
| `poc1_run_id` | str | 元にした PoC 1 の run |
| `audio_path` | str | 推定に使った音声 (記録用) |
| `audio_sha256` | str | |
| `duration_sec` | float | |

### TranscriberInfo

| Field | Type | Rule |
|---|---|---|
| `method` | str | `adtof-pytorch` |
| `version` | str | パッケージのバージョンと git コミット |
| `params` | dict | `thresholds` (楽器ごと)、`fps`、`peak_picking` の各値 |
| `device` | str | `cpu` |

## PlayAlongRecording (演奏の録音)

`output/recordings/<recording_id>/`。`recording.json` + `drums.wav` (録った音声そのまま) + `midi_notes.json`。

| Field | Type | Rule |
|---|---|---|
| `schema_version` | int | 1 |
| `recording_id` | str | `<YYYYMMDD-HHMMSS>_<伴奏の PoC 1 run_id の sha 部分>` |
| `poc1_run_id` | str | 伴奏を取った PoC 1 の run |
| `device` | dict | 入出力デバイス名、サンプルレート、ブロックサイズ、ストリームの入力・出力遅延 (秒) |
| `midi_port` | str | MIDI 入力ポート名 |
| `note_map` | dict | 使った対応表 (R-08) |
| `notes` | MidiNote[] | 受信したノート (`midi_notes.json` に保存) |
| `recorded_at` | str | ISO 8601 |

### MidiNote

| Field | Type | Rule |
|---|---|---|
| `time_sec` | float | 録音開始からの秒数 (`perf_counter` 基準、補正前) |
| `note` | int | 0〜127 |
| `velocity` | int | 1〜127 (velocity 0 の Note On は Note Off として無視) |

## GroundTruth (正解データ)

`groundtruth.json`。電子ドラムは `poc evaluate` が作る。手動アノテーションは `annotation.yaml` + `hits.csv` から読み込んで同じ形にする。

| Field | Type | Rule |
|---|---|---|
| `source` | `"td17_midi"` \| `"manual"` | |
| `target_kind` | `"evaluation_mix"` \| `"poc1_song"` | 評価用の曲か、市販曲か |
| `target_id` | str | recording_id または PoC 1 の run_id |
| `regions` | [start_sec, end_sec][] | 評価する区間。MIDI は最初と最後の打撃 ± 0.5 秒、手動は確認区間 |
| `hits` | GroundTruthHit[] | 区間内のみ |
| `alignment` | MidiAudioAlignment \| null | `td17_midi` のときのみ |

### GroundTruthHit

| Field | Type | Rule |
|---|---|---|
| `time_sec` | float | 評価用の曲 (または原曲) の時間軸 |
| `instrument` | `"kick"` \| `"snare"` \| `"hihat"` | 対象外のパッドは含めない |
| `velocity` | int \| null | 手動は null |
| `ghost` | bool | MIDI: Snare・HiHat で velocity < 40。手動: ラベル末尾 `g` |

### MidiAudioAlignment (SC-008)

| Field | Type | Rule |
|---|---|---|
| `offset_ms` | float | 補正値 (MIDI 時刻 + offset = 音声の時刻)。打撃ごとのずれの中央値 |
| `residual_std_ms` | float | 補正後のずれの標準偏差。≤ 1.0 で SC-008 を満たす |
| `matched_ratio` | float | オンセットと対応が取れた MIDI ノートの割合。< 0.8 なら評価を止める |
| `stream_latency_ms` | float | ドラムを伴奏の時間軸に揃えるためにずらした量 (R-05, R-10) |
| `drum_gain_db` | float | 評価用の曲を作るときのドラムの音量調整 (R-10) |

## TranscriptionEvaluation (評価結果)

`output/evaluations/<evaluation_id>/evaluation.json`。

| Field | Type | Rule |
|---|---|---|
| `schema_version` | int | 1 |
| `evaluation_id` | str | `<YYYYMMDD-HHMMSS>_<target_id>` |
| `groundtruth` | dict | `source`, `target_kind`, `target_id`, `regions` |
| `tolerance_ms` | float | 既定 50 |
| `results` | dict | 入力の種類 (`drum_stem` / `mix`) → InstrumentMetrics の dict (kick / snare / hihat) と transcription_id |
| `ghost_notes` | dict | 楽器ごとの、ゴーストノートの検出数 / 総数 (FR-009) |
| `residual_drum_hits` | dict \| null | 伴奏だけの推定で、区間内に検出された楽器ごとの数 (FR-015)。`td17_midi` のときのみ |

### InstrumentMetrics

| Field | Type | Rule |
|---|---|---|
| `tp` / `fp` / `fn` | int | ゴーストノートを除く |
| `precision` / `recall` / `f1` | float \| null | 分母が 0 なら null |
| `timing_ms` | dict | TP のずれ (推定 − 正解) の `mae` / `median_abs` / `p95_abs` / `median_signed` |
| `strength_spearman` | float \| null | TP の強さと velocity の順位相関 (FR-016)。手動・TP < 5 のときは null |

## TranscriptionSummary (FR-013)

`poc summarize-events` の出力: `output/reports/poc2_summary.md` と `poc2_summary.csv` (1 行 1 評価 × 入力の種類)。
電子ドラムの評価 (SC-001 / 002 / 007 / 008) と手動アノテーションの評価 (SC-009) は分けて集計する。

## Relationships

```text
PoC1 SeparationRun (原曲) ──┬── 1..* TranscriptionRun (drum_stem)              … US1
                            ├── 0..1 GroundTruth (manual) ── 1 TranscriptionEvaluation
                            └── 0..* PlayAlongRecording (伴奏)
                                         │
                                         └── 1 Evaluation Mix ── PoC1 SeparationRun (評価用の曲)
                                                    │                     └── TranscriptionRun (drum_stem)
                                                    ├── TranscriptionRun (mix)                        … US3
                                                    └── GroundTruth (td17_midi) ── 1 TranscriptionEvaluation
PoC1 accompaniment ── TranscriptionRun (accompaniment)  … FR-015
```
