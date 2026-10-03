# Contract: Output Files (PoC 1)

フィールドの定義と検証ルールは [data-model.md](../data-model.md) を参照。ここでは具体的なファイルの形を示す。

## Run ディレクトリ

```text
output/runs/20261004-213000_3fa9c2d1/
├── drums.wav            # 32-bit float WAV。原曲と同じ SR・チャンネル数・サンプル数
├── accompaniment.wav    # 同上 (--no-accompaniment のときは作らない)
├── run.json             # SeparationRun
└── evaluation.yaml      # SeparationEvaluation (開発者が記入)
```

## `run.json` (例)

```json
{
  "schema_version": 1,
  "run_id": "20261004-213000_3fa9c2d1",
  "created_at": "2026-10-04T21:30:00+09:00",
  "status": "succeeded",
  "song": {
    "path": "/Users/me/dev/ai-drum-practice-coach/data/songs/example.m4a",
    "sha256": "3fa9c2d1...",
    "format": "mov,mp4,m4a,3gp,3g2,mj2",
    "codec": "alac",
    "sample_rate": 44100,
    "channels": 2,
    "num_samples": 10584000,
    "duration_sec": 240.0
  },
  "separator": {
    "method": "demucs",
    "version": "4.1.0",
    "model": "htdemucs",
    "params": {"shifts": 0, "overlap": 0.25, "segment": null, "split": true, "seed": 0},
    "device": "mps",
    "model_samplerate": 44100
  },
  "stems": [
    {"kind": "drums", "path": "drums.wav", "sample_rate": 44100, "channels": 2,
     "num_samples": 10584000, "peak": 0.87, "rms_db_relative_to_mix": -6.2},
    {"kind": "accompaniment", "path": "accompaniment.wav", "sample_rate": 44100, "channels": 2,
     "num_samples": 10584000, "peak": 0.95, "rms_db_relative_to_mix": -1.4}
  ],
  "alignment": {
    "method": "stem_sum_xcorr",
    "window_start_sec": 62.0,
    "lag_samples": 0,
    "lag_ms": 0.0,
    "length_match": true,
    "passed": true
  },
  "timings_sec": {"decode": 1.2, "separate": 210.5, "write": 0.8, "total": 213.1},
  "peak_memory": {"rss_bytes": 3221225472, "mps_driver_bytes": 2147483648},
  "environment": {
    "python": "3.11.11", "torch": "2.x.x", "demucs": "4.1.0",
    "ffmpeg": "ffmpeg version 7.x", "platform": "macOS-15.6.1-arm64", "machine": "Apple M1"
  },
  "warnings": []
}
```

- `song.path` は記録用。`run.json` はリポジトリにコミットしない (`output/` は `.gitignore` 済み)
- `schema_version` はフィールドを変えたら上げる。`summarize` は対応していない版を読んだらエラーにする

## `evaluation.yaml` (生成直後のテンプレート)

```yaml
# 評価シート (PoC 1)。記入したら `uv run poc summarize` で集計する。
# 評価の仕方:
#   listening: 1-5 の整数。drum_clarity 5=ドラムがはっきり聴こえる / bleed 5=他楽器の混入なし / artifacts 5=劣化なし
#   sections: Verse・Chorus・Fill 前後から 4 小節ずつ。原曲で聴こえる打撃 (ゴーストノートを除く) を original に、
#             Drum Stem で確認できた打撃を detected に書く。
schema_version: 1
run_id: 20261004-213000_3fa9c2d1
song_label: ""
genre: ""
evaluated_at: ""
listening:
  drum_clarity: null
  bleed: null
  artifacts: null
sections:
  - label: verse
    start_sec: null
    end_sec: null
    counts:
      kick:  {original: null, detected: null}
      snare: {original: null, detected: null}
      hihat: {original: null, detected: null}
    ghost_notes_memo: ""
  - label: chorus
    start_sec: null
    end_sec: null
    counts:
      kick:  {original: null, detected: null}
      snare: {original: null, detected: null}
      hihat: {original: null, detected: null}
    ghost_notes_memo: ""
  - label: fill
    start_sec: null
    end_sec: null
    counts:
      kick:  {original: null, detected: null}
      snare: {original: null, detected: null}
      hihat: {original: null, detected: null}
    ghost_notes_memo: ""
notes: ""
```

`null` が 1 つでも残っているシートは「記入途中」として集計から外す。

## `summary.md` (例)

```markdown
# PoC 1 Evaluation Summary (2026-10-10)

Evaluated songs: 5 (genres: rock, pop, funk, ballad, jazz)

| Criterion | Target | Result | Status |
|---|---|---|---|
| SC-001 Generation success | 100% of ≥5 songs | 5 songs evaluated | PASS |
| SC-002 Hit rate (excl. ghost notes) | ≥ 90% in every song | min 91.2% (kick 98.1 / snare 95.0 / hihat 88.2) | PASS |
| SC-003 Listening (mean) | clarity ≥ 4.0, bleed ≥ 3.0 | clarity 4.2 / bleed 3.4 | PASS |
| SC-004 Alignment | ≤ 1 ms in all songs | max 0.00 ms | PASS |
| SC-005 4-min song time | ≤ 10 min | 3.6 min (normalized) | PASS |
| SC-007 Run records complete | all FR-010 items in every run | 6/6 complete | PASS |

Artifacts (record only): mean 3.8

SC-006 (reproducibility) is checked separately with `poc check-repro`.
```

- SC-005 は「処理時間 ÷ 曲長 × 240 秒」で 4 分の曲に換算した値の最大値で判定する
- SC-002 は曲ごとの確認率の最小値で判定する (すべての曲で 90% 以上)
- SC-001〜SC-003 は、評価済みの曲 (同じ曲の再実行は 1 曲と数える) が 5 曲未満なら `INSUFFICIENT`
- SC-006 は `check-repro`、SC-007 は全 run の `run.json` の必須項目の有無を `summarize` が確認する
