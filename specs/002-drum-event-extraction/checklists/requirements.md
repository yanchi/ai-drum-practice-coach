# Specification Quality Checklist: Drum Event Extraction (PoC 2)

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-04
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- 2026-10-04 初回検証: [NEEDS CLARIFICATION] が 2 件 (正解データの作り方、評価セットの構成)。
- 2026-10-04 回答を反映して再検証: 全項目パス。Q1 = 電子ドラムの MIDI をメイン + 市販曲の手動アノテーションを 1〜2 曲 (併用)、Q2 = PoC 1 のロック 5 曲。
  (Q1 の回答は A → B → C と変わり、C で確定した)
- 2026-10-04 `/speckit.clarify` (2 問: 録音方法 = TD-17 の USB で MIDI と音声を同時録音 / 確認用の出力 = クリック付き WAV + MIDI) と spec レビュー (伴奏に残ったドラムの影響・ハイハットペダル・強さの記録・SC-008 / SC-009 の扱い) を反映して再検証: 全項目パス。
- plan で決める事項: 録音ソフト、伴奏の聴き方と録音音声に伴奏が混ざらないことの確認方法、評価用の曲のミックスの音量バランス、ゴーストノートの velocity 閾値、TD-17 の MIDI ノート番号と楽器の対応、TD-17 のキットの選び方。
- 推定方式 (モデル名) は spec に書かず、`docs/poc-plan.md` の選定を plan で使う。
- 「Precision / Recall / F1」「ms」は技術用語だが、CLAUDE.md の PoC Success Criteria で定義された評価指標のため、そのまま使う。
- 本 PoC の利用者は開発者自身のため、「non-technical stakeholders」はドラマー視点で読める記述であることをもって満たすと判断した。
