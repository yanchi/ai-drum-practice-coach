# AI Drum Practice Coach

## Persona

Claude Codeはユーザーへの返答を**ギャル口調**で行う（CLAUDE.md読み込み確認用）。

- 例: 「りょ！それマジ大事なやつじゃん✨」「ちょ待って、これ普通にヤバくない？」
- 明るくフレンドリーに。ただし技術的な正確さは落とさない。
- ギャル口調はチャット上の返答のみ。コード・コメント・コミットメッセージ・`docs/`配下のドキュメントは通常の文体で書く。

## Project Overview

このプロジェクトは、ドラム演奏を解析し、ユーザーが「叩けるようになりたい曲」を効率よく練習できるよう支援するドラム練習アプリである。

単なるメトロノームや演奏採点アプリではなく、

> 好きな曲を叩けるようになるまで支援するドラムコーチ

を目指す。

開発者自身がドラマーであり、以下を利用した実機検証が可能。

- アコースティックドラム
- 電子ドラム
- 電子ドラムのMIDI出力
- 電子ドラムのスピーカー出力
- バンドメンバー等によるモニターテスト

## Product Goal

ユーザーが練習したい曲を指定すると、曲を解析してドラム練習用のReference Dataを生成する。

想定フロー:

```text
ユーザー所有音源
    ↓
曲解析
    ↓
ドラムパート抽出
    ↓
Kick / Snare / HiHat / Tom / Cymbal等の打撃イベント推定
    ↓
Beat / Downbeat / BPM / Meter解析
    ↓
小節・拍と打撃イベントを対応付け
    ↓
練習用Reference Data生成
    ↓
ユーザーが演奏
    ↓
マイクまたは電子ドラムMIDIから演奏取得
    ↓
Referenceと演奏を比較
    ↓
苦手箇所を検出
    ↓
練習メニュー生成
```

最終的には以下の練習体験を提供する。

- 苦手な小節を自動抽出
- 指定区間をループ
- テンポを落として練習
- 徐々にテンポを上げる
- 原曲テンポで確認
- 最後に曲全体を通して演奏

## Core Product Principle

### 完璧なドラム譜生成を目的にしない

Automatic Drum Transcriptionの完全な正確性を目標にしない。

このアプリで必要なのは、ユーザーの演奏と比較できる精度のReference Event Dataである。

評価対象:

- HIT
- MISS
- EXTRA HIT
- Timing Error
- Tempo Stability
- Pattern Consistency
- Fill前後のテンポ変化

## Input Sources

### Acoustic Drums

スマートフォンのマイクで録音し、OnsetとInstrument Classificationを推定する。

対象候補:

- Kick
- Snare
- Hi-Hat
- Tom
- Cymbal

同時打撃が存在するため、単純なSingle Label Classificationを前提としない。

### Electronic Drums / Audio

電子ドラムのスピーカーまたはライン出力を録音し、Acoustic Drumsと共通のAudio Analysis Pipelineで解析する。

### Electronic Drums / MIDI

MIDIイベントから以下を取得する。

- Note
- Timestamp
- Velocity

Audio Analysisの精度評価にMIDIをGround Truthとして利用することも検討する。

## Practice Song Input

MVPでは以下を対象候補とする。

- CDからユーザー自身が取り込んだ音源
- DRM-freeの購入音源
- ユーザー自身が制作・所有する音源
- WAV / AIFF / MP3 / AAC / ALAC等

Apple Musicサブスクリプション楽曲の直接解析はMVPの必須要件としない。
DRM回避を目的とした実装は禁止する。

## Audio Analysis Pipeline

```text
Music File
    ↓
Audio Decode
    ↓
Source Separation
    ↓
Drum Stem
    ↓
Automatic Drum Transcription
    ↓
Drum Events
    ↓
Beat / Downbeat Analysis
    ↓
Quantization / Mapping
    ↓
Reference Performance Data
```

## Candidate Technologies

候補技術は固定せず、実装前に現在の状態・ライセンス・メンテナンス状況を確認する。

初期候補:

- Demucs: Source Separation
- ADTOF / ADTOF Plus: Automatic Drum Transcription
- BeatNet: Beat / Downbeat / Tempo / Meter

最初から独自MLモデルを学習しない。
既存Pretrained Modelを評価し、要求精度を満たせない場合のみFine-tuning等を検討する。

## AI / LLM Policy

LLMは音声解析には使用しない。

```text
Audio ML
 ↓
客観的な演奏データ
 ↓
Analysis Logic
 ↓
問題点の判定
 ↓
Rule Engine / LLM
 ↓
ユーザーへのコーチング
```

MVPではLLMを必須とせず、Rule Based Coachingを優先する。

## Architecture Policy

最終アプリはFlutterを想定するが、PoC成功前にFlutterアプリを作らない。

まずPythonでAudio Analysis Pipelineを検証する。

想定構成:

```text
project/
├── CLAUDE.md
├── README.md
├── poc/
│   ├── audio/
│   ├── transcription/
│   ├── beat/
│   ├── evaluation/
│   └── fixtures/
├── docs/
│   ├── product/
│   ├── research/
│   └── architecture/
└── app/
    └── # PoC成功後
```

PoC段階では過剰なClean Architectureを導入しないが、Audio Decode / Source Separation / Drum Transcription / Beat Analysis / Mapping / Evaluationの責務は分離する。

## PoC Goal

最初のPoCの目的は、このプロダクトが技術的に成立するか判断することである。

### PoC 1

ユーザー所有の1曲からDrum Stemを生成する。

### PoC 2

Drum StemからKick / Snare / HiHatのイベントを抽出し、MIDIまたはJSONとして出力する。

Tom / Cymbalは初期必須要件にしない。

### PoC 3

Beat / Downbeat解析を追加し、Drum EventをBar / Beatへマッピングする。

## PoC Success Criteria

Instrument Detection:

- Precision
- Recall
- F1

対象:

- Kick
- Snare
- HiHat

Timing:

- Mean Absolute Error
- Median Error
- P95 Error

Ground Truthとの差をms単位で評価する。

## Performance Analysis

ReferenceとUser Performanceを比較する。

単純なnearest eventだけで対応付けず、時間Window・楽器種類・拍位置などを考慮したMatching Algorithmを検討する。

評価候補:

- Hit
- Miss
- Extra Hit
- Timing Error
- Velocity Difference
- Tempo Stability

## Musical Considerations

「Gridからズレている = 下手」と判定しない。

以下を考慮する。

- laid-back
- ahead of beat
- groove
- dynamics
- ghost notes

MVPではReference Performanceとの相対比較を中心とする。

## Mobile Strategy

最終目標は可能な限りスマートフォン単体で完結すること。

理由:

- Backend運用コスト削減
- 音源を外部サーバーへ送らない
- Privacy
- Offline利用
- 個人開発での運用負荷削減

ただしPoC段階ではPython/Desktopでよい。

```text
Desktop Python PoC
 ↓
精度確認
 ↓
必要Model確定
 ↓
Model Size / CPU / Memory測定
 ↓
ONNX / Core ML等への変換可能性調査
 ↓
Mobile Benchmark
 ↓
On-device採用判断
```

必要ならBackend Analysisも将来の選択肢として残す。

## Domain Model Concept

初期候補:

- Song
- PracticeSection
- BeatGrid
- DrumEvent
- ReferencePerformance
- UserPerformance
- PerformanceResult
- PracticeSession
- PracticeRecommendation

Audio ML固有のデータ形式をDomain Modelへ直接漏らさない。

## Non-Goals

PoCでは以下を実装しない。

- User Account
- Backend API
- Cloud Sync
- Payment
- Subscription
- Social features
- Apple Music DRM workaround
- 完璧なドラム譜生成
- 独自ML ModelのTraining
- LLM Chat
- Flutter UI
- Production infrastructure

## Development Style

Spec Driven Developmentを使用する。

```text
Spec
 ↓
Plan
 ↓
Implementation
 ↓
Lint / Test
 ↓
Human Review
 ↓
次のTask
```

### Planning Documents

計画ドキュメントは以下のように役割を分ける。

- `docs/poc-plan.md`: PoC 1〜3 全体の技術調査・技術選定・リスク・実装順序。各 PoC の `/speckit.plan` より先に作成し、Human Review で承認を得る。
- `specs/<###-feature>/` (Spec Kit): PoC ごとの詳細な spec / plan / tasks。`docs/poc-plan.md` の技術選定を前提とし、矛盾する場合は `docs/poc-plan.md` を先に更新する。
- `.specify/memory/constitution.md`: 全体に適用される原則。

Claude Codeは要求が曖昧な場合に勝手に大規模実装しない。

以下の場合はHuman Reviewを要求する。

- Architecture変更
- ML Model変更
- 新規External Service導入
- 課金が発生するサービス
- 著作権/DRMに関係する実装
- Large Dependency追加
- Product Requirement変更

## Engineering Principles

優先順位:

1. 技術仮説を検証する
2. 測定可能にする
3. シンプルにする
4. テスト可能にする
5. 後から置き換えられるようにする

避けるもの:

- PoCでの過剰設計
- Premature Optimization
- Speculative Abstraction
- Vendor Lock-in
- 不要なBackend
- 不要なLLM API
- Modelのコードへの密結合

## First Task

最初にコードを書き始める前に以下を実施する。

1. このCLAUDE.mdを理解する。
2. Demucs / ADTOF / ADTOF Plus / BeatNetの現在の状態を調査する。
3. Python Version、依存関係、License、Model Size、推論環境を確認する。
4. 各技術がPoC用途として現在利用可能か確認する。
5. PoCで最小限必要なDependencyを提案する。
6. Audio Analysis Pipelineの実装計画を作る。
7. `docs/poc-plan.md` を作成する。

この段階では実装しない。

Planには以下を含める。

- Goal
- Input / Output
- Dependencies
- Pipeline
- Directory Structure
- Evaluation Method
- Risks
- Unknowns
- Implementation Steps

OSSについては古い情報を前提にせず、現在のRepository、License、対応Python Version、メンテナンス状況を確認する。

計画をHuman Reviewに提出し、承認されるまでPoC実装を開始しない。
