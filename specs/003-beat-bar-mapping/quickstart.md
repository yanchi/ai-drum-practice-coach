# Quickstart: Beat / Downbeat Analysis and Bar Mapping (PoC 3)

前提: [PoC 2 の quickstart](../002-drum-event-extraction/quickstart.md) を済ませ、評価セット 5 曲 (NO. NEW YORK / B・BLUE / ONLY YOU / WORKING MAN / PLASTIC BOMB) について、
PoC 1 の分離結果 (`output/runs/`)、drum stem の採譜結果 (`output/transcriptions/`)、TD-17 のキャリブレーションがあること。

## 1. 拍と小節の頭を推定する (US1)

```bash
uv run poc beats output/runs/<run_id>                    # output/beatgrids/<beatgrid_id>/
afplay output/beatgrids/<beatgrid_id>/check.wav          # 原曲 + 拍のクリック (小節の頭は高い音)
```

小節の頭の高い音が、曲の小節の頭で鳴っているかを聴く。比較用に `--no-regularize` / `--no-offset` / `--input drum_stem` も作れる。

## 2. 打撃イベントを小節・拍に対応付ける (US2)

```bash
uv run poc map output/beatgrids/<beatgrid_id> output/transcriptions/<transcription_id>
uv run poc bars output/references/<reference_id> 12 13     # 12〜13 小節目の打撃を一覧
```

## 3. 拍の正解を作る (US3)

### 3a. TD-17 で拍を叩く (5 曲すべて)

```bash
uv run poc record output/runs/<run_id> --tap-beats
```

カウントのあと原曲が流れる。**拍ごとにハイハット、小節の頭では同時にキック**を踏む (クリックは鳴らない)。
最後まで叩いたら、標準エラー出力の「叩き損ねの疑い」を確認する。多ければ録り直す。

### 3b. 手で付ける (2〜3 曲・各 1 区間 8 小節程度。167 BPM と 187 BPM の曲を含める)

`data/annotations/<名前>/annotation.yaml` に `beat_regions` を足す (8 小節程度):

```yaml
beat_regions:
  - [29.10, 40.62]
```

```bash
uv run poc annotate data/annotations/<名前>/annotation.yaml --beats
```

全体の波形のレーンをクリックで拍、Shift+クリックで小節の頭。「保存」で `beats.csv` ができる。
打撃の割り当て (SC-004) は、この手で付けた正解で測る (叩いた正解はグリッド位置の判定には粗い。spec Clarifications)。

## 4. 評価する

```bash
uv run poc evaluate-beats output/beatgrids/<beatgrid_id> --taps output/recordings/<recording_id>     # 拍・小節の頭・BPM
uv run poc evaluate-beats output/beatgrids/<beatgrid_id> --annotation data/annotations/<名前>/annotation.yaml   # 打撃の割り当て
uv run poc check-beats output/beatgrids/<id_a> output/beatgrids/<id_b>    # 同じ曲を 2 回推定して一致 (SC-007)
uv run poc summarize-beats                                                 # output/reports/poc3_summary.md
```

結果を `docs/research/poc3-evaluation.md` にまとめ、Go/No-Go の Human Review に出す。

## 5. 開発者向け

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest                 # 合成した拍・打撃イベントで動くテスト
uv run pytest -m slow         # 実際に Beat This! を動かすテスト
```
