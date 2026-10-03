# Quickstart: Drum Event Extraction (PoC 2)

前提: [PoC 1 の quickstart](../001-drum-stem-extraction/quickstart.md) を済ませ、`output/runs/` に評価セット 5 曲 (NO. NEW YORK / B・BLUE / ONLY YOU / WORKING MAN / PLASTIC BOMB) の分離結果があること。
PLASTIC BOMB は PoC 1 の評価セット外のため、`uv run poc separate "data/song/<曲>.m4a"` を先に実行する。

## 0. TD-17 の準備 (最初の 1 回)

1. Roland のサイトから **TD-17 Driver Ver.1.0.3 for macOS** をダウンロードして入れる (Mac の再起動やセキュリティ設定での許可が必要な場合がある)
2. TD-17 で `SETUP → USB → USB Driver Mode` を **VENDOR** にして、TD-17 を再起動する
3. TD-17 と Mac を USB でつなぎ、ヘッドホンを TD-17 に挿す
4. 動作確認:

   ```bash
   uv sync
   uv run poc record --list-devices   # TD-17 の音声デバイスと MIDI ポートが出ること
   uv run poc record --check          # 録音に伴奏が混ざらないこと、パッドのノート番号が正しいこと
   ```

   キットは生ドラムに近い音のキット (プリセットの Acoustic 系) を選ぶ。

5. キャリブレーション (最初に 1 回。キットや機材を変えたらやり直す):

   ```bash
   uv run poc record --calibrate
   ```

   4 回のカウントのあと、1 秒ごとのクリックに合わせて 1 打ずつ叩く (Kick ×8 → Snare ヘッド ×8 → リム ×4 → HiHat クローズ ×8 → オープン ×4 → ペダル ×4)。

## 1. 原曲から打撃イベントを取り出す (US1)

```bash
uv run poc transcribe output/runs/<run_id>
afplay output/transcriptions/<transcription_id>/check.wav   # 原曲 + クリックで確認
```

`events.mid` は原曲と一緒に DAW に読み込める。

## 2. 電子ドラムで録音して評価する (US2, US3)

曲ごとに:

```bash
uv run poc record output/runs/<run_id> --click   # カウントのあと伴奏が流れるので、曲を通して叩く
uv run poc evaluate output/recordings/<recording_id>
```

`--click` を付けると、原曲の拍に合わせたクリック (小節頭は高い音) が伴奏に重なる (research R-18)。

- 拍は Beat This! で検出し、`output/runs/<run_id>/beats.json` に保存する。最初の 1 回は重み (約 78 MB) のダウンロードを含めて 1〜2 分かかる。
- クリックの位置は、その曲の drum stem の最新の採譜結果 (手順 1) に合わせて補正する。採譜結果がないとエラーになるので、先に `poc transcribe` を実行する。
- 小節頭の判定は曲によって乱れる (PLASTIC BOMB など)。拍そのものの位置は合っている。

1 曲にかかった作業時間 (録音 + 評価) をメモしておく (SC-007)。

## 3. 市販曲の手動アノテーション (1〜2 曲)

1. Sonic Visualiser などで原曲を開き、Verse・Chorus・Fill 前後の 4 小節ずつ (計 3 区間) で打撃に印を付ける
   (ラベル: `k` / `s` / `h`、スネアのゴーストノートは `sg`)
2. 時刻とラベルを CSV で書き出し、`data/annotations/<名前>/hits.csv` に置く
3. 同じフォルダに `annotation.yaml` を書く:

   ```yaml
   schema_version: 1
   poc1_run_id: 20261004-004951_3e21c73e
   regions:
     - [45.2, 53.1]
     - [78.0, 85.9]
     - [120.4, 128.3]
   hits_csv: hits.csv
   ```

4. 評価する:

   ```bash
   uv run poc evaluate --annotation data/annotations/<名前>/annotation.yaml
   ```

## 4. 集計する

```bash
uv run poc transcribe output/runs/<run_id>    # 同じ曲を 2 回採譜して
uv run poc transcribe output/runs/<run_id>
uv run poc check-events output/transcriptions/<id_a> output/transcriptions/<id_b>   # 一致すること (SC-005)
uv run poc tune-thresholds      # 閾値の探索 (output/reports/poc2_thresholds.md)
uv run poc summarize-events     # output/reports/poc2_summary.md
```

`summarize-events` は曲ごとに最新の評価を使う。

結果を `docs/research/poc2-evaluation.md` にまとめ、Go/No-Go の Human Review に出す。

## 5. 開発者向け

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest                 # TD-17 なしで動くテスト (合成音源・合成 MIDI)
uv run pytest -m slow         # 実際に Demucs / ADTOF-pytorch / Beat This! を動かすテスト
```
