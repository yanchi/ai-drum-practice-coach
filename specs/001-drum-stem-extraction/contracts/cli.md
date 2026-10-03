# Contract: CLI (PoC 1)

エントリポイント: `uv run poc <command>` (`pyproject.toml` の `[project.scripts]` で `poc = "poc.cli:main"`)。
引数の解析には標準ライブラリの `argparse` を使う。

共通ルール:

- 正常終了は終了コード `0`、ユーザーが原因のエラー (入力不正・DRM 等) は `2`、それ以外の失敗は `1`
- 進捗とエラーは標準エラー出力、結果のパスなど機械で読む値は標準出力に出す
- 楽曲データを外部に送信しない (FR-006)。ネットワークへのアクセスは、初回のモデル重みのダウンロードのみ

---

## `poc separate`

1 曲を分離して、run ディレクトリを作る。

```text
uv run poc separate <audio_path> [--output-dir output/runs] [--device {auto,mps,cpu}] [--seed 0] [--no-accompaniment]
```

| 引数 | 既定値 | 説明 |
|---|---|---|
| `audio_path` | (必須) | 入力楽曲のパス |
| `--output-dir` | `output/runs` | run ディレクトリを作る場所 |
| `--device` | `auto` | `auto` は MPS が使えれば MPS、なければ CPU |
| `--seed` | `0` | 乱数のシード |
| `--no-accompaniment` | off | 伴奏 stem を保存しない |

**成功時**:

- `<output-dir>/<run_id>/` に `drums.wav`、`accompaniment.wav` (省略時を除く)、`run.json`、`evaluation.yaml` (未記入のテンプレート) を作る
- 標準出力: run ディレクトリの絶対パスを 1 行
- 警告がある場合は標準エラー出力にも表示する (終了コードは `0`)

**失敗時**:

| 条件 | 終了コード | メッセージ (標準エラー出力) |
|---|---|---|
| ファイルが存在しない・読めない | 2 | `error: cannot read <path>: <理由>` |
| DRM 保護ファイル | 2 | `error: <path> is DRM-protected and is not supported. Use a CD rip, DRM-free purchase, or your own recording.` |
| 対応外の形式・3 チャンネル以上 | 2 | `error: unsupported audio (<codec>, <channels>ch). Supported: WAV / AIFF / MP3 / AAC / ALAC, mono or stereo.` |
| ffmpeg が見つからない | 1 | `error: ffmpeg not found. Install with: brew install ffmpeg` |
| 分離中のエラー・メモリ不足 | 1 | `error: separation failed: <理由>` |

いずれの失敗でも `<run_id>.partial/` は削除し、run ディレクトリは残さない (FR-014)。

## `poc summarize`

記入済みの評価シートを集計する。

```text
uv run poc summarize [--runs-dir output/runs] [--report-dir output/reports]
```

**成功時**:

- `<report-dir>/summary.csv` と `<report-dir>/summary.md` を作る (既存のファイルは上書きする。集計結果は評価シートからいつでも作り直せるため)
- 標準出力: `summary.md` の内容
- 未記入・記入途中の評価シートはスキップし、その run_id を標準エラー出力に表示する

**失敗時**:

| 条件 | 終了コード |
|---|---|
| 評価シートの値が範囲外・形式が不正 (例: `drum_clarity: 6`、`detected > original`、区間が 3 つでない) | 2 (ファイル名と項目名を表示) |
| 記入済みの評価シートが 0 件 | 2 |

## `poc check-repro`

同じ入力を 2 回分離した結果を比べる (SC-006)。

```text
uv run poc check-repro <run_dir_a> <run_dir_b> [--tolerance 1e-4]
```

- 2 つの run の `song.sha256` と `separator` (`device` 以外) が一致することを確認したうえで、`drums.wav` のサンプルごとの最大絶対差を計算する
- 標準出力: `max_abs_diff=<値> tolerance=<値> result=PASS|FAIL`
- 終了コード: PASS は `0`、FAIL は `1`、入力や設定が一致しない場合は `2`
