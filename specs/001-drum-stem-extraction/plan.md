# Implementation Plan: Drum Stem Extraction (PoC 1)

**Branch**: `001-drum-stem-extraction` | **Date**: 2026-10-03 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-drum-stem-extraction/spec.md`
**Upstream**: [docs/poc-plan.md](../../docs/poc-plan.md) (2026-10-03 承認。技術選定はここに従う)

## Summary

ユーザー所有の楽曲 1 曲から、Demucs v4 (`htdemucs`) で Drum Stem と Accompaniment Stem を作る CLI を Python で実装する。
デコードと DRM 判定は ffmpeg / ffprobe で行い、stem は原曲と同じサンプルレート・チャンネル数・サンプル数の 32-bit float WAV で保存する。
実行ごとに入力ハッシュ・モデル・パラメータ・処理時間・最大メモリ・時間ずれの検証結果 (stem の和と原曲の相互相関) を `run.json` に記録する。
開発者が記入する YAML の評価シート (1 曲ごとの OK / NG と気になった楽器・問題) を集計し、SC-001〜SC-007 を判定するレポートを出力する (2026-10-04 に評価方法を簡素化)。
再現性のため Demucs のランダムな時間シフトは無効化 (`shifts=0`) する。

## Technical Context

**Language/Version**: Python 3.11 (uv で管理)
**Primary Dependencies**: demucs 4.1.0 (torch, julius, pyyaml を含む)、numpy、soundfile。システム依存として ffmpeg / ffprobe (Homebrew)
**Storage**: ローカルファイルのみ。入力は `data/`、出力は `output/runs/<run_id>/` と `output/reports/` (どちらも `.gitignore` 済み)
**Testing**: pytest (単体・パイプライン)、`@pytest.mark.slow` で Demucs を実際に動かす統合テスト。Lint / format は ruff
**Target Platform**: macOS 15 / Apple M1 / メモリ 16GB (MPS、なければ CPU)
**Project Type**: CLI ツール (単一の Python パッケージ `poc`)
**Performance Goals**: 4 分の曲を 10 分以内に処理する (SC-005)。CPU で約 6 分の見込み (Demucs README: 曲長の約 1.5 倍)
**Constraints**: オフラインで処理する (モデル重みの初回ダウンロードを除く)。楽曲と stem をコミットしない。stem と原曲の時間ずれ ≤ 1 ms。同じ入力・同じ設定の再実行で差が ≤ 1e-4
**Scale/Scope**: 評価セットは 5 曲以上。開発者 1 名がローカルで使う

未決事項 (NEEDS CLARIFICATION) はなし。実装上の判断は [research.md](research.md) R-01〜R-14 で決定済み。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution v1.0.1 に対する確認。Phase 1 の設計後に再確認した結果も併記する。

| 原則 / ゲート | 確認内容 | Phase 0 前 | Phase 1 後 |
|---|---|---|---|
| I. Hypothesis-First, Measurable PoC | 検証する仮説 (spec の目的)、定量基準 (SC-001〜007)、再現可能な記録 (`run.json`: 入力ハッシュ・モデル・パラメータ・環境) | PASS | PASS — `summarize` が SC を自動判定し、`check-repro` で再現性を確認する |
| II. Reference-Comparable Accuracy | 完璧な分離を目標にせず、後続の打撃抽出に使えるかで判定 | PASS | PASS — 合否は「PoC 2 の打撃検出に使えるか」の OK / NG で決める。精度の定量評価は PoC 2 で行う |
| III. Separated Pipeline & Replaceable Models | Decode / Separation / Evaluation の分離。Demucs 固有の型を Domain Model に出さない | PASS | PASS — `poc/separation/demucs_adapter.py` の中だけで Demucs を扱う。`Separator` Protocol とテスト用の Fake で差し替えを確認する |
| IV. Copyright, DRM & Privacy | DRM の回避をしない、ユーザー所有の音源のみ、著作物をコミットしない、外部に送信しない | PASS | PASS — DRM は検出して拒否する (復号は試みない)。出力は `output/` (gitignore)。テストは合成信号のみ |
| V. Simplicity & Scope Discipline | UI・Backend・LLM なし、最小限の依存 | PASS | PASS — 新しい Python 依存は demucs / numpy / soundfile のみ (pyyaml / julius は demucs 経由で入る)。評価は YAML + CLI |
| VI. Musically Aware Evaluation | Grid からのずれで判定しない | N/A | N/A — PoC 1 には演奏評価がない。ゴーストノートは確認率から外してメモに残す |
| Review Gate: ML Model 変更 | `docs/poc-plan.md` で承認済みの Demucs `htdemucs` のみ使用 | PASS | PASS |
| Review Gate: Large Dependency | torch (demucs 経由) は `docs/poc-plan.md` で承認済み | PASS | PASS |
| Review Gate: 著作権 / DRM | DRM 判定を実装する | 要 Human Review | PASS — research R-05 の判定方法を 2026-10-03 の Human Review で承認 |
| Review Gate: Architecture | `poc/separation/` の追加は `docs/poc-plan.md` で承認済み | PASS | PASS |

違反なし。Complexity Tracking は不要。

## Project Structure

### Documentation (this feature)

```text
specs/001-drum-stem-extraction/
├── spec.md
├── plan.md              # 本ファイル
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── cli.md           # poc separate / summarize / check-repro
│   └── files.md         # run.json / evaluation.yaml / summary.md
├── checklists/
│   └── requirements.md
└── tasks.md             # /speckit.tasks で作成
```

### Source Code (repository root)

```text
pyproject.toml                    # uv。依存、[project.scripts] poc = "poc.cli:main"、ruff / pytest 設定
poc/
├── __init__.py
├── domain.py                     # Song / Stem / SeparationRun / SeparationEvaluation 等の dataclass
├── cli.py                        # argparse。separate / summarize / check-repro
├── audio/
│   ├── __init__.py
│   ├── probe.py                  # ffprobe 実行、DRM 判定、対応形式チェック
│   ├── decode.py                 # ffmpeg で float32 にデコード
│   └── signal.py                 # リサンプル・サンプル数合わせ・RMS / peak・相互相関による lag
├── separation/
│   ├── __init__.py
│   ├── base.py                   # Separator Protocol (入力: 配列 + SR、出力: drums / accompaniment の配列)
│   └── demucs_adapter.py         # Demucs Separator のラップ (shifts=0、デバイス選択、stem の合成)
├── evaluation/
│   ├── __init__.py
│   ├── run.py                    # separate の全体処理: 計測・警告判定・原子的な保存・run.json
│   ├── sheet.py                  # evaluation.yaml のテンプレート生成・読み込み・検証
│   └── summary.py                # 集計と SC 判定、summary.csv / summary.md
└── fixtures/                     # (既存) 合成信号の生成コードなど、権利上問題のない素材のみ

tests/
├── conftest.py                   # 合成信号のヘルパー、slow マーカー
├── unit/
│   ├── test_probe.py             # DRM 判定・対応形式 (ffprobe の JSON を用意して検証)
│   ├── test_signal.py            # リサンプル往復・長さ合わせ・lag 計算
│   ├── test_sheet.py             # 評価シートの検証ルール
│   └── test_summary.py           # 確認率・SC 判定
├── pipeline/
│   └── test_run.py               # FakeSeparator で run ディレクトリ・run.json・失敗時の後始末を検証
└── integration/
    └── test_demucs.py            # @slow: 合成クリック音源で Demucs を実行
```

**Structure Decision**: `docs/poc-plan.md` §6 の構成のうち、PoC 1 で使う `poc/audio/`、`poc/separation/`、`poc/evaluation/` だけを作る。
`poc/transcription/`、`poc/beat/`、`poc/mapping/` は PoC 2 / 3 で追加する (既存の `.gitkeep` はそのまま残す)。
パイプラインの段は「関数 + 小さな dataclass」で構成し、抽象化は分離方式の差し替え (FR-012) に必要な `Separator` Protocol だけにとどめる。

## Implementation Notes

- **処理の流れ (`poc separate`)**: probe (DRM / 形式) → decode → (SR ≠ 44.1kHz なら) resample → Demucs → resample で元の SR に戻す → サンプル数を合わせる → モノラルの曲ならモノラルにまとめる → stem の peak / RMS の確認 → 相互相関で時間ずれを検証 → `.partial` に WAV と JSON を書く → リネーム
- **SC-005 の換算**: `summarize` は「処理時間 ÷ 曲長 × 240 秒」で 4 分の曲に換算した値で判定する
- **Large file**: 10 分を超える曲も Demucs の `split=True` (分割処理) で処理する。メモリ不足 (MPS / CPU) の例外は捕まえて終了コード `1` にし、`--device cpu` での再実行を案内する

## Phase 2 Preview (`/speckit.tasks` 向け)

User Story の優先度順に、それぞれ単独で確認できる単位に分ける。

1. Setup: `pyproject.toml`、ruff / pytest の設定、ffmpeg の存在確認
2. US1 (P1): probe / decode / signal → Separator Protocol + Demucs adapter → `poc separate` (drums.wav)
3. US3 (P3): `run.json` (計測・環境・警告) と `check-repro` — US1 の出力に記録を追加する形で実装する
4. US2 (P2): `evaluation.yaml` テンプレート → `poc summarize`
5. US4 (P4): accompaniment.wav (US1 の adapter で合成済みのため、保存とオプションのみ)
6. 評価: 5 曲以上で分離・記入・集計 → `docs/research/` にレポート → Go/No-Go

US3 を US2 より先に置くのは、評価 (US2) が `run.json` の値 (時間ずれ・処理時間) を読むため。

## Complexity Tracking

違反なし。
