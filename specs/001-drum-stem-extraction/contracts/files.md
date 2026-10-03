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
# verdict: Drum Stem を聴いて、PoC 2 の打撃検出に使えそうなら ok、使えなさそうなら ng
# issues: 気になった楽器・問題のリスト (例: [hihat, bleed])。なければ []
#   kick / snare / hihat / toms / cymbals = その楽器が消えている・弱い
#   bleed = 他の楽器が混ざる / artifacts = 音質の劣化
schema_version: 2
run_id: 20261004-213000_3fa9c2d1
song_label: "1-10 B・BLUE"
genre: ""
evaluated_at: ""
verdict: null
issues: []
notes: ""
```

`verdict` が `null` のまま、または `song_label` が空のシートは「記入途中」として集計から外す。

## `summary.md` (例)

```markdown
# PoC 1 Evaluation Summary (2026-10-10)

Evaluated songs: 5 (genres: ballad, funk, pop, rock)

| Criterion | Target | Result | Status |
|---|---|---|---|
| SC-001 Generation success | 100% of ≥5 songs | 5 songs evaluated | PASS |
| SC-002 Developer verdict | OK in every song | 5/5 OK | PASS |
| SC-004 Alignment | ≤ 1 ms in all songs | max 0.00 ms | PASS |
| SC-005 4-min song time | ≤ 10 min | 3.6 min (normalized) | PASS |
| SC-007 Run records complete | all FR-010 items in every run | 6/6 complete | PASS |

Issues noted: hihat 1, bleed 2

SC-006 (reproducibility) is checked separately with `poc check-repro`.
```

- SC-001 は、評価済みの曲 (同じ曲の再実行は 1 曲と数える) が 5 曲未満なら `INSUFFICIENT`
- SC-002 は、NG が 1 曲でもあれば曲数に関係なく `FAIL`。NG がなく 5 曲未満なら `INSUFFICIENT`
- SC-003 は廃止 (2026-10-04)
- SC-005 は「処理時間 ÷ 曲長 × 240 秒」で 4 分の曲に換算した値の最大値で判定する
- SC-006 は `check-repro`、SC-007 は全 run の `run.json` の必須項目の有無を `summarize` が確認する
