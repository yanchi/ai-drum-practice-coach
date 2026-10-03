# Quickstart: Drum Stem Extraction (PoC 1)

PoC 1 を手元の Mac で動かし、評価までを行う手順。CLI の詳細は [contracts/cli.md](contracts/cli.md)、
出力ファイルの形式は [contracts/files.md](contracts/files.md) を参照。

## 1. 前提

- macOS (Apple Silicon)、Python 3.11、[uv](https://docs.astral.sh/uv/)
- ffmpeg:

  ```bash
  brew install ffmpeg
  ffmpeg -version
  ```

## 2. セットアップ

```bash
cd ai-drum-practice-coach
uv sync            # 依存をインストール (.venv を作る)
uv run poc --help
```

初回の分離時に Demucs のモデル重み (`htdemucs`) が Hugging Face hub からダウンロードされる。楽曲データは送信されない。

## 3. 楽曲を置く

ユーザー所有の楽曲 (CD 取り込み・DRM-free 購入音源・自作音源) を `data/songs/` に置く。`data/` は Git の管理対象外。

```text
data/songs/
├── 01_rock.m4a
├── 02_pop.mp3
└── ...
```

## 4. 分離する

```bash
uv run poc separate data/songs/01_rock.m4a
# => /.../output/runs/20261004-213000_3fa9c2d1
```

- `drums.wav` を再生して、ドラムが分離できているかを聴く
- 原曲と `drums.wav` を DAW 等に並べて同時に再生し、時間がずれていないことを確認する
- 警告 (例: `drums_nearly_silent`) が出たら `run.json` の `warnings` を確認する

## 5. 評価シートを記入する

`output/runs/<run_id>/evaluation.yaml` をエディタで開いて記入する (1 曲あたり数分)。曲名 (`song_label`) は自動で入っている。

1. `drums.wav` を聴いて、PoC 2 の打撃検出に使えそうなら `verdict: ok`、使えなさそうなら `verdict: ng`
2. 気になった楽器・問題があれば `issues` に書く (例: `issues: [hihat, bleed]`)
   - `kick` / `snare` / `hihat` / `toms` / `cymbals`: その楽器が消えている・弱い
   - `bleed`: 他の楽器が混ざる / `artifacts`: 音質の劣化
3. 必要なら `genre` / `evaluated_at` / `notes` も書く

打撃の数は数えない。打撃の検出精度は PoC 2 で測る。

## 6. 再現性を確認する (SC-006)

評価セットのうち 1 曲を、同じ設定でもう一度分離して比べる。

```bash
uv run poc separate data/songs/01_rock.m4a
uv run poc check-repro output/runs/<1回目の run_id> output/runs/<2回目の run_id>
# => max_abs_diff=0 tolerance=0.0001 result=PASS
```

## 7. 集計する

ジャンルの異なる 5 曲以上で 4〜5 を行ったあと:

```bash
uv run poc summarize
# => output/reports/summary.md と summary.csv
```

`summary.md` の SC-001〜SC-005 の判定と `check-repro` の結果を `docs/research/` の評価レポートにまとめ、Go/No-Go の Human Review に出す。

## 8. 開発者向け: テストと Lint

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest                 # 単体テスト・パイプラインのテスト (モデル不要)
uv run pytest -m slow         # 実際に Demucs を動かす統合テスト (初回はモデルのダウンロードあり)
```
