# Contract: CLI (PoC 2)

PoC 1 の `poc` コマンドにサブコマンドを追加する。終了コード (0 成功 / 1 失敗 / 2 入力の問題)、標準出力・標準エラー出力の使い分け、
`.partial` ディレクトリによる原子的な保存は PoC 1 ([contracts/cli.md](../../001-drum-stem-extraction/contracts/cli.md)) と同じ。

---

## `poc transcribe`

PoC 1 の run から打撃イベントを推定する (US1, US3, FR-015)。

```text
uv run poc transcribe <poc1_run_dir> [--input {drum_stem,mix,accompaniment}] [--output-dir output/transcriptions]
```

| 引数 | 既定値 | 説明 |
|---|---|---|
| `poc1_run_dir` | (必須) | PoC 1 の run ディレクトリ |
| `--input` | `drum_stem` | `drum_stem` = `drums.wav`、`mix` = PoC 1 の入力音声 (分離前)、`accompaniment` = `accompaniment.wav` |

**成功時**: `<output-dir>/<transcription_id>/` に次を作り、ディレクトリの絶対パスを標準出力に出す。

```text
transcription.json   # TranscriptionRun (DrumEvent の一覧を含む)
events.mid           # 確認用 MIDI (General MIDI ドラム)
check.wav            # 原曲 + 楽器ごとのクリック (Kick 150 Hz / Snare 800 Hz / HiHat 4 kHz)
```

**失敗時**: run ディレクトリが不正・指定した音声がない (2)、推定中のエラー (1)。

## `poc record`

TD-17 で伴奏に合わせて叩き、MIDI とドラムの音声を録音する (US2)。

```text
uv run poc record <poc1_run_dir> [--device "TD-17"] [--midi-port "TD-17"] [--output-dir output/recordings]
uv run poc record --check [--device "TD-17"] [--midi-port "TD-17"]
uv run poc record --list-devices
```

- 録音: カウント (4 拍のクリック) のあと伴奏が始まる。伴奏が終わるか Ctrl+C で終了し、`<output-dir>/<recording_id>/` に
  `drums.wav` (録音そのまま)、`midi_notes.json`、`recording.json` を保存する。Ctrl+C の場合も、それまでの録音を保存する
- `--check` (Step 0 の動作確認):
  1. 伴奏の代わりにテスト音を 5 秒流し、何も叩かずに録音して、録音に再生音が混ざらないかを判定する (R-07)
  2. 「各パッドを 1 回ずつ叩いてください」と表示し、受け取ったノート番号と対応表 (R-08) の楽器名を表示する
  3. 結果を `PASS` / `FAIL` で表示する
- `--list-devices`: 音声デバイスと MIDI ポートの一覧を表示する
- デバイスや MIDI ポートが見つからない場合は、ドライバの導入と `USB Driver Mode = VENDOR` の設定を案内して終了コード 2

## `poc evaluate`

正解データと比べて評価する (US2, US3)。

```text
uv run poc evaluate <recording_dir> [--tolerance-ms 50] [--ghost-velocity 40]
uv run poc evaluate --annotation <annotation.yaml> [--tolerance-ms 50]
```

- `<recording_dir>` の場合 (電子ドラム) は次をまとめて行う:
  1. MIDI と音声のずれを測って補正 (SC-008)。`matched_ratio < 0.8` または `residual_std_ms > 1.0` なら終了コード 1 で止める
  2. 評価用の曲 (`mix.wav`) と `groundtruth.json` を recording ディレクトリに作る
  3. 評価用の曲を PoC 1 の分離 (`poc separate` と同じ処理) にかける
  4. `drum_stem` / `mix` / 元の伴奏の `accompaniment` の 3 つで推定する
  5. 対応付けと指標の計算をして、`output/evaluations/<evaluation_id>/evaluation.json` を作る
- `--annotation` の場合 (手動) は、PoC 1 の run の `drum_stem` (と `mix`) の推定結果と比べる
- 標準出力: 楽器ごとの P / R / F1 とタイミング誤差の表

## `poc summarize-events`

すべての評価を集計し、Success Criteria を判定する (FR-013)。

```text
uv run poc summarize-events [--evaluations-dir output/evaluations] [--report-dir output/reports]
```

`poc2_summary.md` / `poc2_summary.csv` を作り、`poc2_summary.md` を標準出力に出す。判定は PASS / FAIL / INSUFFICIENT / N/A (PoC 1 と同じ)。

| 基準 | 判定方法 |
|---|---|
| SC-001 | 電子ドラムの評価 (`drum_stem` 入力) を全曲まとめた楽器ごとの F1 ≥ 0.80 |
| SC-002 | 同じく、楽器ごとの `median_abs` ≤ 10 ms かつ `p95_abs` ≤ 30 ms |
| SC-003 | 電子ドラムの評価が 5 曲 (別の PoC 1 run) 以上、手動アノテーションの評価が 1 曲以上 |
| SC-004 | `drum_stem` の推定時間を 4 分に換算した最大値 ≤ 2 分 |
| SC-006 | すべての `transcription.json` に FR-011 の項目がある |
| SC-008 | すべての電子ドラムの評価で `residual_std_ms` ≤ 1.0 |
| SC-009 | 手動の F1 が、同じ楽器の電子ドラムの F1 − 0.10 以上 (参考値) |

SC-005 は `poc check-events <transcription_a> <transcription_b>` (イベント一覧の一致を確認) で、SC-007 は開発者の作業時間の記録で確認する。

## `poc check-events`

同じ入力・同じ設定で 2 回推定した結果が一致するかを確認する (SC-005)。

```text
uv run poc check-events <transcription_dir_a> <transcription_dir_b>
```

入力の `audio_sha256` と `transcriber` (`device` 以外) が一致することを確認したうえで、イベント一覧 (時刻・楽器・強さ) を比べる。
標準出力: `events_a=<数> events_b=<数> mismatches=<数> result=PASS|FAIL`。終了コードは PASS 0 / FAIL 1 / 入力や設定の不一致 2。
