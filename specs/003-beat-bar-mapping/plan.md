# Implementation Plan: Beat / Downbeat Analysis and Bar Mapping (PoC 3)

**Branch**: `003-beat-bar-mapping` | **Date**: 2026-10-04 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/003-beat-bar-mapping/spec.md`
**Upstream**: [docs/poc-plan.md](../../docs/poc-plan.md) (Beat This! は承認済み)、[PoC 2](../002-drum-event-extraction/plan.md) の実装 (`poc/`)、[PoC 2 評価レポート](../../docs/research/poc2-evaluation.md)

## Summary

原曲から Beat This! (PoC 2 で導入済み) で拍と小節の頭を推定し、BeatGrid を作る。
推定の弱点 (PoC 2 で確認) に対して、取りこぼした拍の補い (R-02)、4/4 を前提にした小節の頭の整理 (Viterbi、R-03)、原曲のドラムへの位置合わせ (R-04) を順に行い、
それぞれの効果を比べられるよう推定そのままの結果も残す。
BeatGrid と PoC 2 の打撃イベントから、各打撃に小節・拍・グリッド位置・ずれを付けた Reference Performance Data を作る (R-05)。
精度は、開発者が原曲に合わせて TD-17 で拍を叩いた曲全体の正解 (R-06) と、手で付けた一部の区間の正解 (R-07) で測る。

## Technical Context

**Language/Version**: Python 3.11 (PoC 1・2 と同じ)
**Primary Dependencies**: PoC 2 までの依存のみ (beat-this 1.1.0 は PoC 2 で追加済み)。**新しい依存はない**
**Storage**: ローカルファイルのみ。`output/beatgrids/`、`output/references/`、`output/beat_evaluations/`、`output/recordings/` (拍を叩いた録音)、`output/reports/`、手で付けた正解は `data/annotations/` (すべて `.gitignore` 済み)
**Testing**: pytest。合成した拍の列・小節の頭の活性値・打撃イベントでテストする。Beat This! を実際に動かすテストは `@pytest.mark.slow` (PoC 2 で追加済み)。拍を叩く録音は実機で手動確認
**Target Platform**: macOS 15 / Apple M1 / 16GB、Roland TD-17 KVX (USB, VENDOR モード)
**Project Type**: CLI ツール (`poc` パッケージに追加)
**Performance Goals**: 4 分の曲の拍の推定と対応付けが 2 分以内 (SC-006)。Beat This! は約 6 秒 (PoC 2)
**Constraints**: 楽曲・推定結果・正解データをコミットしない、外部に送らない。同じ入力で同じ結果 (SC-007)
**Scale/Scope**: 評価セット 5 曲 (各 3〜4 分)、拍を叩く正解 5 曲分、手で付ける正解 1〜2 曲の 1〜2 区間

未決事項 (NEEDS CLARIFICATION) はなし。実装上の判断は [research.md](research.md) R-01〜R-11 で決定済み。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution v1.0.1 に対する確認。

| 原則 / ゲート | 確認内容 | Phase 0 前 | Phase 1 後 |
|---|---|---|---|
| I. Measurable PoC | 定量基準 (SC-001〜009)、再現可能な記録 | PASS | PASS — 正解は曲全体 (叩いた拍) + 手で付けた区間。叩いた正解のブレも測る (SC-005)。`beatgrid.json` / `evaluation.json` に入力ハッシュ・モデル・設定・補正量を記録 |
| II. Reference-Comparable Accuracy | 完璧な譜面ではなく比較に使える精度 | PASS | PASS — グリッド位置は丸めるが、元の位置とずれ (ms) を残す |
| III. Separated Pipeline & Replaceable Models | Beat Analysis と Mapping を分ける。モデル固有の形式を出さない | PASS | PASS — Beat This! の型は `poc/beat/beat_this_adapter.py` の中だけ。`BeatEstimator` Protocol で差し替え可能 (FR-016)。対応付けは `poc/mapping/` |
| IV. Copyright, DRM & Privacy | 著作物をコミットしない、外部に送らない | PASS | PASS — 出力はすべて `output/`、手で付けた正解は `data/` |
| V. Simplicity & Scope Discipline | 最小限の依存、UI なし | PASS | PASS — 新しい依存なし。手で付ける画面は PoC 2 のツールの拡張。整理は 4 状態の Viterbi だけ |
| VI. Musically Aware Evaluation | Grid からのずれで判定しない | PASS | PASS — ずれ (ms) は記録するだけで評価しない。PoC 3 は演奏者の評価をしない |
| Review Gate: ML Model 変更 | `docs/poc-plan.md` で承認済みの Beat This! のみ | PASS | PASS |
| Review Gate: Large / 新規 Dependency | なし | PASS | PASS |
| Review Gate: Architecture 変更 | `poc/mapping/` の追加 | PASS | PASS — `docs/poc-plan.md` §6 の責務分割 (Beat Analysis / Mapping) どおり |

違反なし。

## Project Structure

### Documentation (this feature)

```text
specs/003-beat-bar-mapping/
├── spec.md
├── plan.md              # 本ファイル
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── cli.md           # poc beats / map / bars / record --tap-beats / annotate --beats / evaluate-beats / summarize-beats / check-beats
├── checklists/
│   └── requirements.md
└── tasks.md             # /speckit.tasks で作成
```

### Source Code (repository root)

```text
poc/
├── domain.py                     # + Beat, BeatGrid, BeatPosition, ReferencePerformance, BeatGroundTruth, BeatEvaluation
├── cli.py                        # + beats / map / bars / evaluate-beats / summarize-beats / check-beats、record --tap-beats、annotate --beats
├── beat/
│   ├── base.py                   # BeatEstimator Protocol (入力: 音声 → 拍・小節の頭の時刻と活性値)
│   ├── beat_this_adapter.py      # Beat This! の呼び出し (beats.py の detect_beats をここへ移す)
│   ├── grid.py                   # 拍の補い (fill_beat_gaps を移す)、小節の頭の整理 (Viterbi)、位置合わせ (drum_offset_sec を移す)、BPM・拍子
│   ├── run.py                    # beats の全体処理 (入力の選択、計測、beatgrid.json、check.wav)
│   └── beats.py                  # PoC 2 の録音用クリック (click_beats)。grid.py の関数を使うように整理
├── mapping/
│   ├── __init__.py
│   └── reference.py              # 打撃 → 小節・拍・グリッド位置 (R-05)、reference.json、bars の取り出し
├── recording/
│   ├── record.py                 # + --tap-beats (原曲を再生、MIDI だけ保存)
│   └── taps.py                   # 叩いた MIDI → BeatGroundTruth、叩き損ねの検出
└── evaluation/
    ├── annotate.py               # + --beats (beats.csv の保存・検証)
    ├── annotator.html            # + 拍のレーン
    ├── beat_groundtruth.py       # beats.csv / beat_regions の読み込み
    ├── beats_eval.py             # evaluate-beats (拍・小節の頭の指標、BPM、拍子、打撃の割り当て、叩いた正解のブレ)
    └── beats_summary.py          # summarize-beats と SC 判定

tests/
├── unit/
│   ├── test_grid.py              # 補い、Viterbi の整理 (2 拍ずれの区間・1 拍の小節)、位置合わせ、BPM・拍子
│   ├── test_reference.py         # 小節の頭の直前の打撃、3 連符と 16 分音符、小節 0、拍のない区間
│   ├── test_taps.py              # ハイハット = 拍、キック同時 = 小節の頭、叩き損ねの警告
│   ├── test_beat_groundtruth.py
│   ├── test_beats_eval.py        # F-measure、割り当ての一致 (小節番号の数え方に依存しないこと)
│   └── test_beats_summary.py
└── pipeline/
    └── test_beats_run.py         # FakeBeatEstimator で beats → map → evaluate-beats の流れ
```

**Structure Decision**: Beat Analysis は既存の `poc/beat/`、Mapping は新しい `poc/mapping/` に置く (Constitution III の責務分割)。
PoC 2 の録音用クリック (`poc/beat/beats.py`) が持っていた補い・位置合わせの関数は `grid.py` に移し、クリックと BeatGrid で同じ実装を使う。
抽象化は推定方式の差し替え (FR-016) に必要な `BeatEstimator` Protocol だけにとどめる。

## Implementation Notes

- **時間軸**: BeatGrid・打撃イベント・正解はすべて原曲の時間軸。PoC 1 で原曲と drum stem のずれは 0 サンプル
- **整理の効果の確認**: Viterbi の整理は、PoC 2 で乱れが分かっている 3 曲 (PLASTIC BOMB / WORKING MAN / ONLY YOU のイントロ) を最初に `check.wav` で聴いて確かめる
- **叩く正解の録り方**: 最初に 1 曲 (B・BLUE、小節の頭の推定がきれいな曲) でパイロットを行い、叩き損ねの警告と、手で付けた区間とのブレを見てから残り 4 曲を録る
- **録音用クリックとの関係**: `poc record --click` は引き続き `beats.json` (PoC 2) を使う。BeatGrid に置き換えるかは PoC 3 の評価の後で決める

## Phase 2 Preview (`/speckit.tasks` 向け)

1. Foundational: Domain Model の追加、`BeatEstimator` Protocol、`detect_beats` / `fill_beat_gaps` / `drum_offset_sec` の移動 (PoC 2 のテストが通ること)
2. US1 (P1): adapter (活性値) → 補い → Viterbi の整理 → 位置合わせ → BPM・拍子 → `poc beats` → `check.wav` を 3 曲で試聴
3. US2 (P1): 対応付け → `poc map` → `poc bars`
4. US3 (P2): `--tap-beats` → BeatGroundTruth → `annotate --beats` → `evaluate-beats` → `summarize-beats` / `check-beats`
5. US4 (P3): `--input drum_stem` の推定と評価
6. 評価: 5 曲の拍を叩く (B・BLUE でパイロット)、手で付ける区間 1〜2 → `docs/research/poc3-evaluation.md` → Go/No-Go

## Complexity Tracking

違反なし。
