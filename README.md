# AI Drum Practice Coach

好きな曲を叩けるようになるまで支援するドラム練習アプリ。

現在は **PoC フェーズ**。Python で Audio Analysis Pipeline（音源分離 → ドラム採譜 → Beat/Downbeat 解析 → 小節・拍マッピング）が成立するかを検証している。

- 方針: [CLAUDE.md](CLAUDE.md)、[Constitution](.specify/memory/constitution.md)
- PoC 全体の計画と技術選定: [docs/poc-plan.md](docs/poc-plan.md)
- PoC ごとの spec / plan / tasks: [specs/](specs/)

## PoC 1: Drum Stem Extraction

ユーザー所有の楽曲からドラムだけの音源 (Drum Stem) を作る。詳細は [quickstart](specs/001-drum-stem-extraction/quickstart.md)。

```bash
brew install ffmpeg
uv sync

uv run poc separate data/songs/<曲>.m4a   # output/runs/<run_id>/ に drums.wav ・ accompaniment.wav ・ run.json ・ evaluation.yaml
# evaluation.yaml に verdict (ok / ng) と気になった点を記入
uv run poc summarize                       # output/reports/summary.md に Success Criteria の判定
uv run poc check-repro <run_a> <run_b>     # 同じ曲の 2 回の実行結果が一致するか
```

テストと Lint:

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest            # モデル不要のテスト
uv run pytest -m slow    # 実際に Demucs を動かすテスト
```

## Directory

```text
poc/
├── audio/          # Audio Decode・DRM 判定・信号処理
├── separation/     # Source Separation (Demucs adapter)
├── transcription/  # Automatic Drum Transcription (PoC 2)
├── beat/           # Beat / Downbeat / Tempo 解析 (PoC 3)
├── evaluation/     # 実行記録・評価シート・集計
└── fixtures/       # テスト用の小さな素材（著作物はコミットしない）
tests/              # pytest (合成音源のみ使用)
specs/              # Spec Kit の spec / plan / tasks
docs/
├── product/
├── research/       # PoC の評価レポート
└── architecture/
app/                # Flutter アプリ（PoC 成功後）
```

## Audio files

市販楽曲などの著作物はリポジトリにコミットしない。ローカルの `data/` に置く。分離結果は `output/` に出力される（どちらも `.gitignore` 済み）。
DRM で保護された音源は解析しない。
