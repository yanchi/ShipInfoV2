# Feature Specification: 便無し（no_service）ステータスの追加

**Feature Branch**: `3-no-service-status`
**Created**: 2026-03-08
**Status**: Draft

## 概要

「便無し」（当日便が存在しない）と「欠航」（便が設定されていたが運航中止）を区別できるようにする。現状は便無し時も `cancelled` として記録しており、データの意味が不正確。新たに `no_service` ステータスを追加し、2社のスクレイパーで正しく使い分けることが目標。

---

## User Scenarios & Testing

### User Story 1 - 便無し日に正しいステータスが記録される (Priority: P1)

スクレイパー運用者として、「当日便がそもそも存在しない日」と「便は設定されていたが欠航になった日」を区別したデータが欲しい。これにより、欠航率の集計や利用者への情報提供が正確になる。

**Why this priority**: データの意味的正確さが最優先。`no_service` が正しく記録されなければ下流の表示・集計が全て誤る。

**Independent Test**: スクレイパーを便無し日・欠航日それぞれに実行し、DB に記録されるステータスが異なることを確認することで単独テスト可能。

**Acceptance Scenarios**:

1. **Given** 当日便が存在しない日, **When** スクレイパーが実行される, **Then** `operation_statuses.status = no_service` で記録され `cancelled` は使われない
2. **Given** 便は存在するが欠航になっている日, **When** スクレイパーが実行される, **Then** `operation_statuses.status = cancelled` で記録される
3. **Given** 便が存在し通常運航の日, **When** スクレイパーが実行される, **Then** `operation_statuses.status = operating` で記録される

---

### User Story 2 - マリックスライン・マルエーフェリー両社で区別が有効 (Priority: P1)

2社のスクレイパー担当者として、どちらの会社でも同じ区別ロジックが働くことを保証したい。

**Why this priority**: US1 と同優先度。片社だけ対応ではデータの一貫性が保てない。

**Independent Test**: 両社のスクレイパーテストで便無しシナリオを追加し、それぞれ `no_service` が返ることを確認。

**Acceptance Scenarios**:

1. **Given** マルエーフェリーの便無し日, **When** スクレイパーが実行される, **Then** `no_service` が記録される
2. **Given** マリックスラインの便無し日, **When** スクレイパーが実行される, **Then** `no_service` が記録される

---

### User Story 3 - 既存の `cancelled` / `operating` / `delayed` / `suspended` に影響がない (Priority: P2)

既存データ・ロジックへの後方互換性を担保したい。

**Why this priority**: `no_service` 追加によって既存ステータスの挙動が変わってはならない。

**Independent Test**: 既存のユニットテスト全件が引き続きパスすることで確認。

**Acceptance Scenarios**:

1. **Given** 欠航の HTML, **When** パース, **Then** `cancelled` のまま変わらない
2. **Given** 通常運航の HTML, **When** パース, **Then** `operating` のまま変わらない
3. **Given** 既存のユニットテスト一式, **When** 実行, **Then** 全件パス

---

### Edge Cases

- 両社で「便無し」の判定方法が異なる場合、それぞれのスクレイパー固有の判定ロジックが `no_service` を返すことを保証する
- `no_service` 記録後に再スクレイピングした場合、`raw_html_hash` により二重記録されないこと
- DB の `status` カラムの型変更（ENUM拡張）が既存レコードに影響しないこと

---

## Requirements

### Functional Requirements

- **FR-001**: システムは「当日便が存在しない」状態を表す `no_service` ステータス値をサポートしなければならない
- **FR-002**: マルエーフェリースクレイパーは、便なし（検索エンドポイントで便が見つからない）時に `no_service` を記録しなければならない
- **FR-003**: マリックスラインスクレイパーは、便なし状態を検出した時に `no_service` を記録しなければならない
- **FR-004**: `no_service` は `cancelled`（欠航）とは別のステータス値でなければならない
- **FR-005**: `no_service` 追加後も既存ステータス（`operating`, `cancelled`, `delayed`, `suspended`）の動作は変わらないこと
- **FR-006**: `no_service` ステータス値は、DB・バックエンドアプリ・スクレイパーの全レイヤーで整合していなければならない

### Key Entities

- **OperationStatusEnum**: `operating` / `cancelled` / `delayed` / `suspended` に `no_service` を追加
- **operation_statuses**: `status` カラムが `no_service` を受け付けること
- **Route**: 変更なし

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: 便無し日にスクレイパーを実行すると `no_service` が DB に記録される（`cancelled` は使われない）
- **SC-002**: 欠航日にスクレイパーを実行すると `cancelled` が DB に記録される（`no_service` は使われない）
- **SC-003**: 既存のユニットテスト全件（マルエーフェリー・マリックスライン・BaseScraper）が変更後もパスする
- **SC-004**: 2社のスクレイパーテストに「便無し → `no_service`」シナリオが追加され、パスする

---

## Assumptions

- マリックスラインの「便無し」判定方法は実装調査フェーズ（plan）で確定する（スクレイパー実装から判断）
- DB の ENUM 変更はマイグレーションで対応（既存データは変更なし）
- Web 表示側（Symfony/Twig）での `no_service` の見せ方は本 spec のスコープ外（別 spec で対応）
- `raw_html_hash` の重複防止ロジックは既存のまま流用

---

## Out of Scope

- `no_service` のフロントエンド表示（別機能として別途対応）
- 過去データの `cancelled` → `no_service` への遡及修正
- 3社目以降のスクレイパーへの対応
