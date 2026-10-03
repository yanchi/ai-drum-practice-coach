# Implementation Plan: Drum Event Extraction (PoC 2)

**Branch**: `002-drum-event-extraction` | **Date**: 2026-10-04 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/002-drum-event-extraction/spec.md`
**Upstream**: [docs/poc-plan.md](../../docs/poc-plan.md) (ADTOF-pytorch は承認済み)、[PoC 1](../001-drum-stem-extraction/plan.md) の実装 (`poc/`)

## Summary

PoC 1 の Drum Stem から、ADTOF-pytorch (コミット固定) で Kick / Snare / HiHat / Tom / Cymbal の打撃イベント (時刻・楽器・強さ) を推定し、
Domain Model の DrumEvent として保存する。確認用に、原曲に楽器ごとのクリックを重ねた WAV と MIDI も出す。
精度は、PoC 1 の伴奏を TD-17 で流しながら叩いた演奏 (USB で MIDI と音声を同時に録音) を正解にして測る。
録った音声を伴奏の時間軸に揃えて重ねた「評価用の曲」を PoC 1 の分離にかけ、推定結果と MIDI を許容範囲 ±50 ms の 1 対 1 対応で比べて、
楽器ごとの P / R / F1 とタイミング誤差を出す。分離前の音声からの推定 (US3) と、伴奏に残った元のドラムの影響 (FR-015) も同時に測る。
市販曲 1〜2 曲は手動アノテーションで参考評価する。

## Technical Context

**Language/Version**: Python 3.11 (PoC 1 と同じ。librosa 0.11 / scipy 1.17 になる。research R-04)
**Primary Dependencies**: PoC 1 の依存 + adtof-pytorch (git `85c192e`)、librosa、pretty_midi、scipy、**sounddevice、python-rtmidi (新規)**
**Storage**: ローカルファイルのみ。`output/transcriptions/`、`output/recordings/`、`output/evaluations/`、`output/reports/`、手動アノテーションは `data/annotations/` (すべて `.gitignore` 済み)
**Testing**: pytest。TD-17 なしで動くよう、合成音源と合成 MIDI でテストする。ADTOF-pytorch を実際に動かすテストは `@pytest.mark.slow`。録音 (`poc record`) は実機で手動確認
**Target Platform**: macOS 15 / Apple M1 / 16GB、Roland TD-17 KVX (USB, VENDOR モード)
**Project Type**: CLI ツール (PoC 1 の `poc` パッケージに追加)
**Performance Goals**: 4 分の曲の打撃イベント推定が 2 分以内 (SC-004)。CPU で十分と見込む (モデル 3.6 MB)
**Constraints**: 楽曲・伴奏・録音・正解データをコミットしない、外部に送らない。推定は同じ入力で同じ結果 (SC-005)。MIDI と音声のずれ補正後のばらつき ≤ 1 ms (SC-008)
**Scale/Scope**: 電子ドラムの評価 5 曲 (各 4 分前後)、手動アノテーション 1〜2 曲 (各約 12 小節)

未決事項 (NEEDS CLARIFICATION) はなし。実装上の判断は [research.md](research.md) R-01〜R-15 で決定済み。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution v1.0.1 に対する確認。

| 原則 / ゲート | 確認内容 | Phase 0 前 | Phase 1 後 |
|---|---|---|---|
| I. Measurable PoC | 定量基準 (SC-001〜009)、再現可能な記録 | PASS | PASS — 正解は MIDI (機械的に正確)。`transcription.json` / `evaluation.json` に入力ハッシュ・方式・コミット・閾値・環境を記録 |
| II. Reference-Comparable Accuracy | 完璧な採譜ではなく比較に使える精度。Single Label を前提としない | PASS | PASS — 楽器ごとに独立したイベント。評価は Kick / Snare / HiHat のみ |
| III. Separated Pipeline & Replaceable Models | モデル固有の形式を Domain Model に出さない | PASS | PASS — ADTOF のクラス番号・活性値は `poc/transcription/adtof_adapter.py` の中だけ。TD-17 のノート番号は `poc/recording/` の対応表の中だけ。`Transcriber` Protocol で差し替え可能 |
| IV. Copyright, DRM & Privacy | 著作物をコミットしない、外部に送らない | PASS | PASS — 伴奏・評価用の曲・録音はすべて `output/`。手動アノテーションは `data/` |
| V. Simplicity & Scope Discipline | 最小限の依存、UI なし | 要 Human Review | PASS — sounddevice と python-rtmidi の追加を 2026-10-04 の Human Review で承認 |
| VI. Musically Aware Evaluation | Grid からのずれで判定しない。nearest event だけに頼らない | PASS | PASS — 正解は開発者の演奏そのもの (Grid ではない)。1 対 1 の最適な対応付け (R-11)。ゴーストノートは別集計 |
| Review Gate: ML Model 変更 | `docs/poc-plan.md` で承認済みの ADTOF-pytorch のみ | PASS | PASS |
| Review Gate: Large / 新規 Dependency | adtof-pytorch / librosa / pretty_midi は承認済み。**sounddevice (MIT) と python-rtmidi (MIT 系) は新規** | 要 Human Review | PASS — 2026-10-04 Human Review で承認。どちらも小さなライブラリ (PortAudio / RtMidi のラッパー)。DAW で録音する代替案より再現性が高い (R-04, R-05) |
| Review Gate: 外部機材・システム変更 | Roland 公式ドライバの導入 (開発者の Mac) | 要 Human Review | PASS — 2026-10-04 Human Review で承認。リポジトリの依存にはしない。開発者が自分で入れる |
| Review Gate: ライセンス | ADTOF の重みは CC BY-NC-SA | PASS | PASS — PoC での使用は承認済み (poc-plan R1)。製品化の前に再判断 |

違反なし。Human Review が必要だった 2 項目 (新規依存 2 つ、TD-17 ドライバの導入) は 2026-10-04 に承認済み。

## Project Structure

### Documentation (this feature)

```text
specs/002-drum-event-extraction/
├── spec.md
├── plan.md              # 本ファイル
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── cli.md           # poc transcribe / record / evaluate / summarize-events / check-events
├── checklists/
│   └── requirements.md
└── tasks.md             # /speckit.tasks で作成
```

### Source Code (repository root)

```text
poc/
├── domain.py                     # + DrumEvent, TranscriptionRun, GroundTruth, GroundTruthHit, InstrumentMetrics など
├── cli.py                        # + transcribe / record / evaluate / summarize-events / check-events
├── transcription/
│   ├── __init__.py
│   ├── base.py                   # Transcriber Protocol (入力: 音声ファイル → DrumEvent[])
│   ├── adtof_adapter.py          # ADTOF-pytorch の呼び出し、活性値 → 強さ、クラス番号 → 楽器名
│   ├── run.py                    # transcribe の全体処理 (入力の選択、計測、transcription.json)
│   └── render.py                 # check.wav (クリック) と events.mid
├── recording/
│   ├── __init__.py
│   ├── td17_note_map.yaml        # TD-17 のノート番号 → 楽器 (R-08)
│   ├── devices.py                # sounddevice / python-rtmidi のデバイス検索
│   ├── record.py                 # duplex ストリームでの再生・録音、MIDI 受信 (実機のみ)
│   ├── check.py                  # --check (ループバック判定、ノート番号の表示)
│   ├── calibration.py            # パッドごとの MIDI と音声のずれの測定 (R-06)
│   └── mix.py                    # 評価用の曲と GroundTruth の作成 (R-10)
├── evaluation/                   # (PoC 1 の run.py / sheet.py / summary.py / metrics.py / repro.py は既存)
│   ├── matching.py               # 1 対 1 の対応付けと指標 (R-11)
│   ├── groundtruth.py            # 手動アノテーションの読み込み (R-13)
│   ├── events_eval.py            # evaluate の全体処理 (分離 → 3 つの入力で推定 → 評価)
│   └── events_summary.py         # summarize-events と SC 判定
└── separation/                   # (PoC 1 のまま。evaluate から run_separation を呼ぶ)

tests/
├── unit/
│   ├── test_matching.py          # 1 対 1 対応・許容範囲・指標・ゴースト除外
│   ├── test_calibration.py       # 合成音でのパッドごとのずれ測定
│   ├── test_mix.py               # 遅延補正・音量調整・GroundTruth の時刻
│   ├── test_groundtruth.py       # hits.csv / annotation.yaml の読み込みと検証
│   ├── test_note_map.py          # TD-17 の対応表、ペダル (44) = hihat、CC は無視
│   ├── test_render.py            # クリックの位置と MIDI ノート
│   └── test_events_summary.py
├── pipeline/
│   └── test_events_eval.py       # FakeTranscriber + FakeSeparator で evaluate の流れ
└── integration/
    └── test_adtof.py             # @slow: 合成ドラム音で ADTOF-pytorch を実行
```

**Structure Decision**: `docs/poc-plan.md` §6 の `poc/transcription/` を使う。録音は TD-17 という外部機材に依存し、評価用データを作るための仕組みなので `poc/recording/` に分ける。
PoC 1 の `poc/evaluation/` (評価シート・集計) とファイル名が衝突しないよう、PoC 2 の集計は `events_*.py` とする。
抽象化は、推定方式の差し替え (FR-012) に必要な `Transcriber` Protocol だけにとどめる。

## Implementation Notes

- **Step 0 (最初に実機で確認)**: TD-17 のドライバを入れたあと、`poc record --list-devices` と `--check` が通ることを確認してから録音系のタスクを進める。
  macOS 15 でドライバが動かない場合は、録音方法を見直すために Human Review に戻す (代替: TD-17 の Generic モードで MIDI のみ録り、音声はライン出力から録る)
- **評価の流れ**: `evaluate` は、PoC 1 の `run_separation` をそのまま使って評価用の曲を分離する (コードを複製しない)
- **時間軸**: 評価用の曲・Drum Stem・推定結果・正解データは、すべて伴奏 (= 評価用の曲) の時間軸で揃える
- **ADTOF-pytorch の出力**: 推定結果には Tom・Cymbal も残す (FR-002)。評価では除外する

## Phase 2 Preview (`/speckit.tasks` 向け)

1. Setup: 依存の追加 (Human Review 後)、`poc/transcription/` と `poc/recording/` の作成
2. Foundational: Domain Model の追加、`Transcriber` Protocol
3. US1 (P1): ADTOF adapter → `poc transcribe` → `check.wav` / `events.mid` → 5 曲で試聴
4. Step 0: TD-17 の準備と `poc record --list-devices` / `--check`
5. US2 (P2): 対応表 → 録音 → キャリブレーション → 評価用の曲 → 対応付けと指標 → `poc evaluate` → 手動アノテーションの読み込み → `poc summarize-events`
6. US3 (P3): `mix` 入力の推定と比較 (evaluate の中で一緒に実行)
7. 評価: 5 曲の録音・評価、手動アノテーション 1〜2 曲 → `docs/research/poc2-evaluation.md` → Go/No-Go

## Complexity Tracking

違反なし。
