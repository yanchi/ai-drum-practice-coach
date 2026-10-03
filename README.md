# AI Drum Practice Coach

好きな曲を叩けるようになるまで支援するドラム練習アプリ。

現在は **PoC前の計画フェーズ**。Python で Audio Analysis Pipeline（音源分離 → ドラム採譜 → Beat/Downbeat 解析 → 小節・拍マッピング）が成立するかを検証する。

詳細な方針は [CLAUDE.md](CLAUDE.md)、PoC 計画は `docs/poc-plan.md`（作成予定）を参照。

## Directory

```text
poc/
├── audio/          # Audio Decode / Source Separation
├── transcription/  # Automatic Drum Transcription
├── beat/           # Beat / Downbeat / Tempo 解析
├── evaluation/     # Ground Truth との比較・指標計算
└── fixtures/       # テスト用の小さな音源・MIDI（著作物はコミットしない）
docs/
├── product/
├── research/
└── architecture/
app/                # Flutter アプリ（PoC 成功後）
```

## Audio files

市販楽曲などの著作物はリポジトリにコミットしない。ローカルの `data/` に置く（`.gitignore` 済み）。
