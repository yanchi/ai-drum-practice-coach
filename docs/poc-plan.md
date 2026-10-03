# PoC Plan: Audio Analysis Pipeline

- **Status**: Approved (2026-10-03 Human Review)
- **Created**: 2026-10-03
- **調査時点**: 2026-10-03 (GitHub / PyPI の現在の状態を直接確認)
- **関連**: [CLAUDE.md](../CLAUDE.md) / [Constitution](../.specify/memory/constitution.md) /
  [PoC 1 spec](../specs/001-drum-stem-extraction/spec.md)

本ドキュメントは PoC 1〜3 全体の技術調査・技術選定・リスク・実装順序を定める。
各 PoC の詳細な spec / plan / tasks は `specs/<###-feature>/` (Spec Kit) で扱い、本ドキュメントの選定を前提とする。

### Review Decisions (2026-10-03)

| 項目 | 決定 |
|---|---|
| Beat 解析モデル | BeatNet を不採用とし、Beat This! を採用する (ML Model 変更として承認) |
| 将来の課金・有料配布 (U1) | 未定。ただし有料化の可能性ありとして扱う。PoC は ADTOF-pytorch で技術成立性を検証し、製品化判断の前に R1 (非商用ライセンス) を再判断する |
| 新規 Dependency | ffmpeg (Homebrew) と PoC 1 の Python 依存の追加を承認。PoC 2 / 3 の依存は各 PoC の開始時に追加する |

---

## 1. Goal

ユーザー所有の楽曲から、ユーザー演奏と比較可能な Reference Performance Data
(Bar / Beat に対応付けられた Kick / Snare / HiHat の打撃イベント) を生成できるかを判断する。

| PoC | 検証する仮説 | Go/No-Go の判断材料 |
|---|---|---|
| PoC 1 | 市販楽曲から、後続処理に使える品質の Drum Stem を手元の Mac で得られる | [PoC 1 spec](../specs/001-drum-stem-extraction/spec.md) の SC-001〜SC-007 |
| PoC 2 | Drum Stem から Kick / Snare / HiHat の打撃イベントを、ユーザー演奏と比較できる精度で抽出できる | 楽器別 Precision / Recall / F1、タイミング誤差 (MAE / Median / P95, ms) |
| PoC 3 | Beat / Downbeat を推定し、打撃イベントを Bar / Beat に正しく対応付けられる | Beat / Downbeat の検出精度、打撃イベントの小節・拍への割り当て正解率 |

## 2. Input / Output

### Input

- ユーザー所有の楽曲ファイル: WAV / AIFF / MP3 / AAC / ALAC (CD 取り込み、DRM-free 購入音源、自作音源)
- DRM 保護ファイル (例: `.m4p`) は対象外。検出して解析せずに終了する
- 楽曲ファイルはリポジトリ外のローカル `data/` に置く (`.gitignore` 済み)

### Output

| PoC | 出力 | 形式 |
|---|---|---|
| PoC 1 | Drum Stem / Accompaniment Stem | WAV (非圧縮, 原曲と同じ長さ・時間軸) |
| PoC 1 | 実行記録 (Separation Run) | JSON |
| PoC 1 | 聴感評価の記録 (OK / NG と気になった楽器) | 開発者が記入する YAML、集計結果 CSV / Markdown |
| PoC 2 | Drum Events (時刻・楽器・強さ) | JSON (+ 確認用 MIDI) |
| PoC 3 | BeatGrid (beat / downbeat 時刻、推定 BPM・拍子) と Bar / Beat 付き Drum Events | JSON |

出力 JSON は ML モデル固有の形式ではなく、Domain Model (Song / BeatGrid / DrumEvent /
ReferencePerformance) に変換した形で保存する (Constitution III)。

## 3. 技術調査結果

### 3.1 Source Separation (PoC 1)

| 候補 | Repository 状態 | License | Python | 所見 |
|---|---|---|---|---|
| **Demucs v4 (htdemucs)** | `facebookresearch/demucs` は **archived**。公式メンテナンスは `adefossez/demucs` に移行。v4.1.0 (2026-07-11) リリース。ただし作者は「新機能の追加予定なし、返信は遅い」と明記 | MIT | >=3.10 | 4 stem (drums / bass / other / vocals)。v4.1.0 で推論から torchaudio 依存が外れ、モデルは Hugging Face hub (safetensors) から取得。出力は 44.1kHz ステレオ WAV。CPU では曲長の約 1.5 倍の処理時間 (README 記載) |
| Demucs `htdemucs_ft` | 同上 | MIT | 同上 | 4 モデルの bag。品質は上がるが処理時間は約 4 倍 → SC-005 (4 分曲を 10 分以内) を CPU で満たせない見込み |
| MDX23C (drum 特化) | `xavriley/mdx23c-drum-separation` (2025-09 更新) | MIT (コード) / 重みは未確認 | — | ADTOF Plus で使用。ドラムキットの個別分離 (kick / snare / hihat 等) にも対応。チェックポイント約 500MB |
| python-audio-separator | 活発 (2026-10 更新) | MIT | >=3.10 | BS-RoFormer / MDX 系モデルを統一 API で扱える。モデルごとに重みのライセンスが異なる |
| Spleeter | 更新はあるが TensorFlow 2.12 固定、Python <3.12 | MIT | 3.8–3.11 | 品質は Demucs v4 より低い世代。不採用 |
| Open-Unmix | 2024-06 以降更新なし | MIT | — | 品質は Demucs v4 より低い世代。不採用 |

**選定: Demucs v4.1.0 `htdemucs`** (PoC 1 spec FR-012 に従い 1 方式から開始)。
未達時の第 2 候補は MDX23C (drum) → python-audio-separator 経由の RoFormer 系の順で検討する。

### 3.2 Automatic Drum Transcription (PoC 2)

| 候補 | Repository 状態 | License | Python | 所見 |
|---|---|---|---|---|
| ADTOF (オリジナル) | `MZehren/ADTOF` (2025-09 更新)。Python 3.10 / macOS で動作確認と記載 | **CC BY-NC-SA 4.0 (非商用)** | 3.10 | TensorFlow / Keras + madmom 依存。5 クラス (kick / snare / hihat / toms / cymbals) |
| **ADTOF-pytorch** | `xavriley/ADTOF-pytorch` (2025-11 更新) | LICENSE ファイルなし。**重みは ADTOF からの変換のため CC BY-NC-SA を継承すると考えるべき** | >=3.9 | 依存は torch / librosa / pretty_midi / numpy のみ。F-measure はオリジナル比 約 -0.2% (MDBDrums++: 88.51 vs 88.74)。重みはパッケージに同梱 |
| ADTOF Plus | `xavriley/adtof_plus_drum_transcription` (2025-11 更新)。論文: "Enhanced Automatic Drum Transcription via Drum Stem Source Separation" (ISMIR 2024 LBD) | README 上は MIT だが LICENSE ファイルなし。ADTOF 重み (NC) と **essentia (AGPL-3.0)** に依存 | >=3.8 | MDX23C でドラム分離 → キット個別分離 → ADTOF で採譜。7 クラス化と velocity 推定を追加 |
| Omnizart | 2026-05 更新、PyPI 0.6.3 | MIT | >=3.8 | ドラム採譜モードあり。ADTOF より精度は低いとされる世代。未評価 |
| MT3 | 2026-09 更新 | Apache-2.0 | — | 多楽器採譜。JAX / T5X ベースで重く、モバイル化に不向き。未評価 |

**選定: ADTOF-pytorch** (PoC 用途。ライセンスはリスク R1 を参照)。
Kick / Snare / HiHat 以外の 2 クラス (toms / cymbals) も出力されるが、PoC 2 の評価対象は 3 クラスに限定する。
ADTOF Plus は精度改善の候補だが、AGPL 依存と約 500MB の追加モデルのため、ADTOF-pytorch 単体で未達だった場合のみ評価する。

### 3.3 Beat / Downbeat / Tempo / Meter (PoC 3)

| 候補 | Repository 状態 | License | Python | 所見 |
|---|---|---|---|---|
| BeatNet | 2026-04 にトレーニングスクリプト追加のみ。PyPI 最終 2023-11 | コード CC BY 4.0 | 実質 <=3.9 | **`numba==0.54.1` 固定**と madmom 依存のため Python 3.10+ でのインストールが困難。offline モードは madmom の DBN を使用 |
| madmom | GitHub は 2026-03 更新、**PyPI 最終 2018 (0.16.1)、Python <3.10 のみ** | コード BSD / **モデル CC BY-NC-SA** | GitHub 版のみ 3.10+ | BeatNet / DBN 後処理の依存。PoC では依存しない |
| **Beat This!** | `CPJKU/beat_this` (2026-05 更新)、PyPI 1.1.0 (2026-04)。ISMIR 2024 | **コード・重みとも MIT** | torch>=2 | beat と downbeat を出力。DBN 後処理なしで高精度。モデル: `final0` 約 78MB / `small0` 約 8.1MB |

**選定: Beat This!** (CLAUDE.md の初期候補 BeatNet から変更)。
BeatNet は依存関係が現行 Python で成立せず、Beat This! はライセンス・メンテナンス・モバイル向けの小型モデルの面で優位。
Beat This! は BPM / 拍子を直接出力しないため、beat 間隔から BPM を、downbeat 間の beat 数から拍子を算出する。

> CLAUDE.md の Candidate Technologies (BeatNet) からの変更は **ML Model 変更** に当たるため、本 Plan の Human Review で承認を得る。

### 3.4 手元の実行環境 (確認済み)

| 項目 | 値 |
|---|---|
| マシン | MacBook Air, Apple M1, メモリ 16GB |
| OS | macOS 15.6.1 |
| Python | 3.11.11 (Homebrew) / uv 0.12.3 |
| ffmpeg | **未インストール** (MP3 / AAC / ALAC のデコードに必要) |

## 4. Dependencies (最小構成案)

| 依存 | 用途 | 導入 PoC | 備考 |
|---|---|---|---|
| Python 3.11 | 実行環境 | 1 | インストール済み。Demucs (>=3.10) / Beat This! / ADTOF-pytorch (>=3.9) を満たす |
| uv | 環境・依存管理 | 1 | インストール済み |
| ffmpeg (Homebrew) | 圧縮音源のデコード、DRM 判定 (ffprobe) | 1 | **新規のシステム依存** |
| torch | 推論基盤 | 1 | 全モデル共通。Large Dependency |
| demucs==4.1.0 | Source Separation | 1 | |
| numpy / soundfile | 音声配列・WAV 入出力 | 1 | |
| pytest / ruff | Test / Lint | 1 | dev 依存 |
| adtof-pytorch (git) | Drum Transcription | 2 | PyPI 未公開。コミットハッシュで固定 |
| librosa / pretty_midi | ADTOF-pytorch の依存、確認用 MIDI 出力 | 2 | |
| beat-this==1.1.0 | Beat / Downbeat | 3 | 依存: torchaudio / einops / rotary-embedding-torch / soxr |

採用しないもの: TensorFlow、madmom、BeatNet、essentia (AGPL)、mir_eval (評価指標は自前で実装する。窓内マッチングと P/R/F1・誤差統計のみで小さいため)。

## 5. Pipeline

```text
Music File (data/)
  │
  ├─ [audio]          Decode・DRM 判定・メタ情報 (SR, ch, 長さ, ハッシュ)
  │                    └→ Song
  ├─ [separation]     Demucs htdemucs
  │                    └→ Drum Stem / Accompaniment Stem (WAV)          … PoC 1
  ├─ [transcription]  ADTOF-pytorch (入力: Drum Stem)
  │                    └→ DrumEvent[] (time, instrument, strength)       … PoC 2
  ├─ [beat]           Beat This! (入力: 原曲ミックス)
  │                    └→ BeatGrid (beats, downbeats, BPM, meter)         … PoC 3
  ├─ [mapping]        DrumEvent → Bar / Beat / 拍内位置
  │                    └→ ReferencePerformance                            … PoC 3
  └─ [evaluation]     PoC ごとの指標算出・実行記録・集計
```

設計上の決定:

- **Beat 解析は Drum Stem ではなく原曲ミックスに対して行う**。ベースやコード進行は downbeat 推定の重要な手がかりのため。Drum Stem 入力との比較は PoC 3 で行う。
- 各段は「ファイルを入力して Domain Model を返す関数」として分離し、モデル呼び出しは各段の adapter に閉じ込める (Constitution III)。
- サンプルレート: Demucs は 44.1kHz で処理・出力する。原曲が 44.1kHz 以外の場合、Stem を原曲の SR に戻すか、時刻を秒で扱って SR 差を吸収するかは PoC 1 の plan で決める。

## 6. Directory Structure

```text
project/
├── pyproject.toml            # uv 管理。PoC 共通の依存
├── poc/
│   ├── domain.py             # Song / DrumEvent / BeatGrid / ReferencePerformance (dataclass)
│   ├── audio/                # decode・DRM 判定・メタ情報
│   ├── separation/           # Demucs adapter                    ← 追加
│   ├── transcription/        # ADTOF-pytorch adapter
│   ├── beat/                 # Beat This! adapter・BPM / 拍子算出
│   ├── mapping/              # DrumEvent → Bar / Beat            ← 追加
│   ├── evaluation/           # 指標・実行記録・集計
│   ├── cli.py                # PoC ごとのコマンド
│   └── fixtures/             # 権利上問題のない小さな音源・注釈
├── tests/                    # pytest (fixtures を使用、実楽曲は使わない)
├── data/                     # (gitignore) 楽曲・手動アノテーション
└── output/                   # (gitignore) Stem・実行記録・評価結果
```

CLAUDE.md の想定構成からの差分: `poc/separation/` と `poc/mapping/` を追加する (Source Separation と Mapping の責務分離のため)。`poc/audio/` は Decode のみを担当する。

## 7. Evaluation Method

### 7.1 PoC 1: Drum Stem

[PoC 1 spec](../specs/001-drum-stem-extraction/spec.md) に従う。要点:

- 評価セット: ジャンルの異なる市販楽曲 5 曲以上
- 聴感評価: 1 曲ごとに「PoC 2 の打撃検出に使えるか」の OK / NG と、気になった楽器・問題のメモ (2026-10-04 に簡素化。打撃の精度は PoC 2 で測る)
- 時間ずれ 1ms 以下 (SC-004) の検証: **Drum Stem + Accompaniment Stem の和と原曲の相互相関のピーク位置が 0 サンプルであること**、および原曲と Stem の長さの一致で確認する
- 処理時間・最大メモリを実行記録に残す

### 7.2 PoC 2: Drum Events

- **Ground Truth**: 評価曲ごとに確認区間 (例: 4 小節 × 3 区間。具体的な量は PoC 2 の spec で決める) を選び、開発者が打撃時刻と楽器を手動アノテーションする。
  アノテーションには波形・スペクトログラムを表示できる外部ツール (例: Sonic Visualiser。リポジトリの依存にはしない) を使い、CSV で書き出して `data/` に置く。
  補助として、電子ドラムで録音した自作曲の MIDI (完全な正解) を追加できる。
- **マッチング**: 楽器ごとに、推定イベントと正解イベントを許容窓 (初期値 ±50ms) 内で 1 対 1 対応付ける
- **指標**: 楽器別 Precision / Recall / F1、対応付いたペアのタイミング誤差の MAE / Median / P95 (ms)
- 手動アノテーションの誤差 (数 ms 程度を想定) は、同じ区間を 2 回アノテーションした差で見積もり、結果に併記する

### 7.3 PoC 3: Beat / Mapping

- **Ground Truth**: 確認区間の beat / downbeat 時刻を手動アノテーション (PoC 2 と同じ作業で付与)
- **指標**: beat / downbeat の F-measure (許容窓 ±70ms)、推定 BPM の誤差、拍子の一致、
  確認区間内の Drum Events が正しい小節・拍に割り当てられた割合

### 7.4 共通

- すべての実行で、入力ハッシュ・モデル名とバージョン・パラメータ・処理時間・最大メモリを JSON に記録する (Constitution I)
- 同じ入力・同じ設定で同じ結果が出ることを確認する (乱数要素は固定する)

## 8. Risks

| ID | リスク | 影響 | 対策 |
|---|---|---|---|
| R1 | **ADTOF の重み (ADTOF-pytorch・ADTOF Plus を含む) と madmom のモデルは CC BY-NC-SA (非商用)** | 有料アプリ・課金を伴う配布に使えない可能性 | PoC (個人の検証) では使用する。製品化の前に、作者へのライセンス確認、許諾の緩いモデルへの置き換え、または自前学習のいずれかを判断する。Domain Model とモデルを分離し、置き換えコストを抑える |
| R2 | Demucs は公式メンテナンスが継続しているが新機能の予定なし | 将来の Python / torch 更新に追随できない可能性 | バージョン固定。差し替え可能な adapter 構造にする。第 2 候補 (MDX23C / RoFormer 系) を保持 |
| R3 | Demucs の HiHat 分離品質 (高域が other に漏れる) | PoC 1 SC-002、PoC 2 の HiHat Recall が未達 | PoC 1 の評価シートの `issues` で HiHat の問題を記録し、早期に検知する。定量的には PoC 2 で楽器別に測る |
| R4 | Demucs の推論にランダムな時間シフトが含まれる設定がある | 再現性 (SC-006) が崩れる | PoC 1 の plan でシフト設定とシード固定を確認する |
| R5 | 手動アノテーションの精度・作業量 | タイミング誤差の評価が Ground Truth の誤差に埋もれる | 区間を限定 (1 曲約 12 小節)。2 回アノテーションで誤差を見積もる。自作曲 MIDI を補助に使う |
| R6 | M1 / 16GB での処理時間・メモリ | SC-005 未達 | CPU で約 1.5× 曲長の見込み (4 分曲で約 6 分)。MPS 利用は Unknown U2 で確認 |
| R7 | モバイル化 (ONNX / Core ML) の難しさ | On-device 採用判断に影響 | PoC では測定のみ (モデルサイズ・時間・メモリ)。変換可能性の調査は PoC 成功後 |
| R8 | 解析対象の著作物・DRM | 法的リスク | DRM 保護ファイルは検出して拒否。楽曲・Stem はコミットしない (Constitution IV) |

## 9. Unknowns

| ID | 不明点 | 確認方法 / タイミング |
|---|---|---|
| U1 | 将来の製品で課金・有料配布を予定しているか | **解決済み**: 未定だが可能性ありとして扱う (Review Decisions 参照) |
| U2 | Demucs / ADTOF-pytorch / Beat This! が M1 の MPS (GPU) で動くか、CPU との速度差 | PoC 1 / 2 / 3 の初期ステップで計測 |
| U3 | Demucs `htdemucs` のモデルサイズ・ピークメモリ | PoC 1 で計測 |
| U4 | ADTOF-pytorch が Demucs の Drum Stem に対して十分な精度を出すか (学習時は分離していない音源) | PoC 2 で評価。Stem 入力と原曲入力の両方を比較する |
| U5 | Beat This! の downbeat 推定が拍子の変わる曲・ルバート曲で破綻しないか | PoC 3 の評価セットに含めるか判断 |
| U6 | MDX23C drum モデルの重みのライセンス | 第 2 候補として使う場合に確認 |
| U7 | 44.1kHz 以外の原曲に対する時間軸の扱い | PoC 1 の plan で決定 |

## 10. Implementation Steps

各 PoC は Spec Kit のフロー (`/speckit.specify` → `/speckit.clarify` → `/speckit.plan` → `/speckit.tasks` →
`/speckit.implement`) で進め、PoC ごとに Go/No-Go を Human Review で判断する。

| Step | 内容 | 成果物 | Gate |
|---|---|---|---|
| 0 | 本 Plan の Human Review | 承認済み `docs/poc-plan.md` | **Human Review** — 2026-10-03 完了 |
| 1 | 環境構築: ffmpeg 導入、`pyproject.toml` (uv, Python 3.11)、ruff / pytest | 動作する空のパッケージ | — |
| 2 | PoC 1 plan / tasks (`specs/001-drum-stem-extraction/`) | plan.md / tasks.md | Human Review |
| 3 | PoC 1 実装: audio (decode・DRM 判定) → separation → 実行記録 → 評価シートと集計 | Drum Stem、実行記録 | Lint / Test |
| 4 | PoC 1 評価: 市販楽曲 5 曲以上で SC-001〜SC-007 を確認 | [評価レポート](research/poc1-evaluation.md) | **Go/No-Go** — 2026-10-04 Go |
| 5 | PoC 2 spec〜plan。確認区間と手動アノテーションの形式を決め、アノテーションする | spec / plan、Ground Truth CSV | Human Review |
| 6 | PoC 2 実装: transcription adapter → DrumEvent JSON / MIDI → 評価 (P/R/F1・誤差) | Drum Events、評価レポート | **Go/No-Go** |
| 7 | PoC 3 spec〜plan | spec / plan | Human Review |
| 8 | PoC 3 実装: beat adapter → BPM / 拍子算出 → mapping → 評価 | ReferencePerformance JSON、評価レポート | **Go/No-Go** |
| 9 | PoC 総括: 精度・処理時間・メモリ・モデルサイズ・ライセンスのまとめと、モバイル化調査の要否判断 | `docs/research/` の総括 | Human Review |

## Sources

- Demucs: <https://github.com/adefossez/demucs> (release notes: `docs/release.md`), <https://github.com/facebookresearch/demucs> (archived), <https://pypi.org/project/demucs/>
- ADTOF: <https://github.com/MZehren/ADTOF>
- ADTOF-pytorch: <https://github.com/xavriley/ADTOF-pytorch>
- ADTOF Plus: <https://github.com/xavriley/adtof_plus_drum_transcription>, <https://arxiv.org/abs/2509.24853>, <https://ismir2024program.ismir.net/lbd_482.html>
- MDX23C drum separation: <https://github.com/xavriley/mdx23c-drum-separation>
- essentia: <https://github.com/MTG/essentia>
- BeatNet: <https://github.com/mjhydri/BeatNet>, <https://pypi.org/project/BeatNet/>
- madmom: <https://github.com/CPJKU/madmom>, <https://pypi.org/project/madmom/>
- Beat This!: <https://github.com/CPJKU/beat_this>, <https://arxiv.org/abs/2407.21658>, <https://pypi.org/project/beat-this/>
- python-audio-separator: <https://github.com/nomadkaraoke/python-audio-separator>
- Spleeter: <https://github.com/deezer/spleeter> / Open-Unmix: <https://github.com/sigsep/open-unmix-pytorch>
- Omnizart: <https://github.com/Music-and-Culture-Technology-Lab/omnizart> / MT3: <https://github.com/magenta/mt3>
