<!--
Sync Impact Report
==================
Version change: 1.0.0 → 1.0.1
Bump rationale: PATCH。原則・セクションの意味は変えず、例示している ML Model 名を
docs/poc-plan.md の承認済み技術選定 (BeatNet → Beat This!、ADTOF → ADTOF-pytorch) に合わせた。

Modified principles:
  - III. Separated Pipeline & Replaceable Models: 例示モデル名のみ更新
Modified sections:
  - Technical Constraints: OSS の例示に Beat This! を追加
Added sections: なし
Removed sections: なし

Templates requiring updates:
  - ✅ .specify/templates/*.md — 変更不要
  - ✅ CLAUDE.md — Candidate Technologies を同日更新済み

Follow-up TODOs: なし
-->

# AI Drum Practice Coach Constitution

## Core Principles

### I. Hypothesis-First, Measurable PoC

- すべての PoC 作業は、検証する技術仮説を明文化してから開始しなければならない (MUST)。
- 各 PoC は定量的な成功基準を持たなければならない (MUST)。
  - Instrument Detection: Kick / Snare / HiHat ごとの Precision / Recall / F1
  - Timing: Ground Truth との差の Mean Absolute Error / Median Error / P95 Error (ms)
- 評価は再現可能でなければならない (MUST)。入力・使用モデルとそのバージョン・パラメータ・
  結果を記録し、同じ入力から同じ指標を再計算できること。
- 電子ドラムの MIDI 出力など、取得可能な Ground Truth を評価に優先的に利用する (SHOULD)。

**Rationale**: このプロジェクトの第一目的は「プロダクトが技術的に成立するか」の判断である。
測定できない改善は判断材料にならない。

### II. Reference-Comparable Accuracy over Perfect Transcription

- 完璧なドラム譜生成 (Automatic Drum Transcription の完全な正確性) を目標にしてはならない (MUST NOT)。
- 精度要件は「ユーザーの演奏と比較して HIT / MISS / EXTRA HIT / Timing Error /
  Tempo Stability / Pattern Consistency を判定できるか」で定義しなければならない (MUST)。
- 初期必須楽器は Kick / Snare / HiHat とする。Tom / Cymbal は初期必須要件にしない。
- 同時打撃が存在するため、Single Label Classification を前提とした設計をしてはならない (MUST NOT)。

**Rationale**: 価値は「好きな曲を叩けるようになるまで支援すること」にあり、
楽譜の完全性ではない。過剰な精度追求は PoC を停滞させる。

### III. Separated Pipeline & Replaceable Models

- Audio Decode / Source Separation / Drum Transcription / Beat Analysis / Mapping / Evaluation
  の責務は分離しなければならない (MUST)。各段は入出力を明示し、単独で実行・テストできること。
- ML Model (Demucs / ADTOF-pytorch / Beat This! 等) 固有のデータ形式を Domain Model
  (Song, BeatGrid, DrumEvent, ReferencePerformance 等) に直接漏らしてはならない (MUST NOT)。
  モデル出力は境界で変換する。
- モデルの差し替えが、該当段以外のコード変更を必要としない構造にする (SHOULD)。
- 既存 Pretrained Model を先に評価しなければならない (MUST)。独自モデルの Training は
  要求精度を満たせないと測定で示された場合にのみ検討する。

**Rationale**: 候補 OSS の状態・ライセンス・モバイル対応は変わり得る。
将来の ONNX / Core ML 変換や On-device 化に備え、モデルとコードの密結合を避ける。

### IV. Copyright, DRM & Privacy (NON-NEGOTIABLE)

- DRM 回避を目的とした実装をしてはならない (MUST NOT)。Apple Music 等のサブスクリプション楽曲の
  直接解析は MVP 要件としない。
- 解析対象はユーザー所有の音源 (CD 取り込み、DRM-free 購入音源、自作音源) に限る (MUST)。
- 市販楽曲などの著作物をリポジトリにコミットしてはならない (MUST NOT)。ローカルの
  `data/` (`.gitignore` 済み) に置く。`poc/fixtures/` には権利上問題のない小さな素材のみ置く。
- ユーザー音源を外部サーバーへ送信する実装は、Human Review の承認なしに追加してはならない (MUST NOT)。

**Rationale**: 著作権・DRM 違反はプロダクトの存続を脅かす。また Privacy と Offline 利用は
On-device 戦略の主要な理由である。

### V. Simplicity & Scope Discipline

- PoC 段階では過剰設計・Premature Optimization・Speculative Abstraction を導入してはならない (MUST NOT)。
- 以下は PoC で実装しない: User Account, Backend API, Cloud Sync, Payment, Subscription,
  Social features, LLM Chat, Flutter UI, Production infrastructure。
- PoC 成功前に Flutter アプリを作ってはならない (MUST NOT)。
- 音声解析に LLM を使用してはならない (MUST NOT)。コーチングは Rule Based を優先し、
  LLM は MVP の必須要件としない。
- 依存は PoC の仮説検証に必要な最小限に留める (MUST)。

**Rationale**: 個人開発で運用負荷とコストを抑え、技術仮説の検証に集中するため。

### VI. Musically Aware Evaluation

- 「Grid からズレている = 下手」と判定してはならない (MUST NOT)。
- 演奏評価は Reference Performance との相対比較を中心とする (MUST)。
- Matching は単純な nearest event のみに依存してはならない (MUST NOT)。時間 Window・
  楽器種類・拍位置を考慮する。
- laid-back / ahead of beat / groove / dynamics / ghost notes を評価設計で考慮する (SHOULD)。

**Rationale**: ドラマーにとって意図的なタイミングのズレは表現であり、
それを誤りと判定するコーチは信頼されない。

## Technical Constraints

- PoC は Python / Desktop で実装する。最終アプリは Flutter を想定する。
- OSS (Demucs / ADTOF / ADTOF Plus / Beat This! 等) は採用前に現在の Repository・License・
  対応 Python Version・メンテナンス状況・Model Size を確認しなければならない (MUST)。
  古い情報を前提にしない。
- 入力ソースは Acoustic Drums (マイク録音)、Electronic Drums (Audio 出力)、
  Electronic Drums (MIDI: Note / Timestamp / Velocity) の 3 系統を想定する。
  Acoustic と Electronic Audio は共通の Audio Analysis Pipeline で扱う。
- 最終目標はスマートフォン単体での完結 (On-device) とする。Backend Analysis は
  将来の選択肢として残すが、PoC では導入しない。
- 対応音源形式の候補: WAV / AIFF / MP3 / AAC / ALAC。

## Development Workflow & Review Gates

- Spec Driven Development を用いる: Spec → Plan → Implementation → Lint / Test →
  Human Review → 次の Task。
- 要求が曖昧な場合、大規模実装を始めてはならない (MUST NOT)。まず確認する。
- 以下の変更は Human Review の承認を得るまで実施してはならない (MUST NOT):
  - Architecture 変更
  - ML Model 変更
  - 新規 External Service 導入
  - 課金が発生するサービス
  - 著作権 / DRM に関係する実装
  - Large Dependency 追加
  - Product Requirement 変更
- 実装は Lint / Test を通過してから Human Review に提出する (MUST)。
- コード・コメント・コミットメッセージ・`docs/` 配下のドキュメントは通常の文体で書く。

## Governance

- 本憲法はプロジェクトの他の慣行に優先する。CLAUDE.md はランタイムの開発ガイダンスとして
  本憲法と整合していなければならない。
- 改訂は、変更内容と理由を記録し、Human Review の承認を得て行う。改訂時は
  `.specify/templates/` 配下および CLAUDE.md への影響を確認し、Sync Impact Report を更新する。
- バージョニングは Semantic Versioning に従う:
  - MAJOR: 原則の削除、または後方互換性のない再定義
  - MINOR: 原則・セクションの追加、またはガイダンスの実質的な拡張
  - PATCH: 文言の明確化、誤字修正など意味を変えない修正
- すべての Plan は "Constitution Check" で本憲法への適合を確認しなければならない。
  違反がある場合は plan の Complexity Tracking に理由と、より単純な代替案を却下した理由を記載する。

**Version**: 1.0.1 | **Ratified**: 2026-10-03 | **Last Amended**: 2026-10-03
