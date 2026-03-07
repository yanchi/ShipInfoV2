# Tasks: 運航情報Webサイト

**Input**: Design documents from `/specs/website/`
**Prerequisites**: plan.md, spec.md, data-model.md, contracts/http-routes.md, research.md, quickstart.md

**Tests**: Constitution準拠のPHPUnitテストをPolishフェーズに含む（spec.mdでTDD明示なし）

**Organization**: US1（トップページ）→ US2（会社別ページ）の優先順位。US3（航路別ページ）はP3のためスコープ外。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 並列実行可能（別ファイル・依存なし）
- **[Story]**: 対応するユーザーストーリー（US1/US2）
- 各タスクに正確なファイルパスを記載

---

## Phase 1: Setup（共有インフラ）

**Purpose**: BootstrapによるUIベース整備。全ページが依存する。

- [x] T001 `app/templates/base.html.twig` に Bootstrap 5 CDN（CSS/JS）・`charset=UTF-8` メタタグ・`viewport` メタタグ・`{% block title %}` を追加し、モバイル対応の基盤を整える

**Checkpoint**: `base.html.twig` を継承すれば全テンプレートで Bootstrap が使える状態

---

## Phase 2: Foundational（ブロッキング前提条件）

**Purpose**: Repositoryクエリメソッドの実装。Controller・テンプレートより先に必ず完了すること。

**⚠️ CRITICAL**: このフェーズ完了前にControllerもテンプレートも実装できない

- [x] T002 `app/src/Repository/OperationStatusRepository.php` に `findTodayByAllCompanies(): array` を追加する。DQL で `active=true` の FerryCompany・Route を JOIN し、`valid_date = TODAY` の OperationStatus を LEFT JOIN。同一 `(route_id, valid_date)` の重複レコードは `MAX(scraped_at)` サブクエリで最新1件に絞る。戻り値は `$companyId => ['company' => FerryCompany, 'routes' => [$routeId => ['route' => Route, 'status' => OperationStatus|null]]]` のネスト配列

- [x] T003 `app/src/Repository/OperationStatusRepository.php` に `findRecentByCompany(FerryCompany $company, int $days = 3): array` を追加する（T002完了後）。DQL で `valid_date >= (TODAY - $days days)` の OperationStatus を取得し、各 `(route_id, valid_date)` の最新1件を `MAX(scraped_at)` で絞る。戻り値は `'Y-m-d' => [$routeId => ['route' => Route, 'status' => OperationStatus|null]]` の日付降順ネスト配列

**Checkpoint**: Repositoryメソッド2本が実装済み。Controller実装を開始できる状態

---

## Phase 3: User Story 1 - トップページ（Priority: P1）🎯 MVP

**Goal**: `http://localhost:8080/` で本日の全社・全航路の運航状況を一覧表示する

**Independent Test**: `http://localhost:8080/` にアクセスして、マルエーフェリー・マリックスラインの運航状況が表示されること。DBに当日データがない場合は「現在情報がありません」が表示され、500エラーにならないこと（SC-004）

### Implementation for User Story 1

- [x] T004 [US1] `app/src/Controller/StatusController.php` を新規作成し、`index()` アクションを実装する。`OperationStatusRepository::findTodayByAllCompanies()` を呼び出し、`companies` と `today`（`new \DateTimeImmutable()`）をテンプレートに渡す。Symfony Routingアノテーション `#[Route('/', name: 'app_status_index')]` を設定する

- [x] T005 [US1] `app/templates/status/index.html.twig` を新規作成する。`base.html.twig` を継承し、本日の日付タイトルを表示、`companies` をループして会社名（`/company/{id}` リンク）・公式サイトリンク（`websiteUrl` が非nullの場合のみ、`target="_blank"`）・各航路のステータスバッジ（operating=`bg-success`/✓、delayed=`bg-warning`/●、cancelled=`bg-danger`/✗、suspended/unknown=`bg-secondary`）を表示する。`companies` が空またはステータスが全nullの場合は「現在情報がありません」メッセージを表示する（FR-001・FR-003・FR-004・SC-001〜004対応）

**Checkpoint**: `http://localhost:8080/` でトップページが表示される。US1の全Acceptance Scenariosが満たされる状態

---

## Phase 4: User Story 2 - 会社別ページ（Priority: P2）

**Goal**: `http://localhost:8080/company/{id}` で特定会社の直近3日分の運航状況を表示する

**Independent Test**: `http://localhost:8080/company/1` にアクセスして直近3日分の運航状況が日付順で表示されること。欠航便の `statusDetail`（理由）が表示されること。`http://localhost:8080/company/999` にアクセスして404が返ること（FR-002・FR-005対応）

### Implementation for User Story 2

- [x] T006 [US2] `app/src/Controller/StatusController.php` に `company(int $id)` アクションを追加する。`FerryCompanyRepository::find($id)` がnullの場合は `$this->createNotFoundException()` をthrow（404）。`OperationStatusRepository::findRecentByCompany($company, 3)` を呼び出し、`company` と `statuses` をテンプレートに渡す。Symfony Routingアノテーション `#[Route('/company/{id}', name: 'app_status_company')]` を設定する（FR-002・FR-005対応）

- [x] T007 [US2] `app/templates/status/company.html.twig` を新規作成する。`base.html.twig` を継承し、`app_status_index` へ「< トップへ戻る」リンク・会社名・公式サイトリンク（`websiteUrl` 非nullの場合のみ）を表示。`statuses` を日付ごとにループして各航路のステータスバッジ（index.html.twigと同じカラーコーディング）と `statusDetail`（非nullの場合のみ）を表示する（FR-002・FR-003・FR-004対応）

**Checkpoint**: US1・US2がそれぞれ独立して動作する。存在しないIDで404が確認できる状態

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: テスト・最終動作確認

- [x] T008 [P] `app/tests/Repository/OperationStatusRepositoryTest.php` を新規作成し、`findTodayByAllCompanies()` と `findRecentByCompany()` のPHPUnitテストを追加する（DataFixtures使用、最新レコード取得・データなし時の空配列返却を検証）

- [x] T009 [P] `app/tests/Controller/StatusControllerTest.php` を新規作成し、`GET /` のレスポンス200・`GET /company/1` のレスポンス200・`GET /company/999` のレスポンス404をWebTestCaseで検証する

- [x] T010 `make test-php` を実行してPHPUnitがグリーンであることを確認し、`quickstart.md` の手順に従って `http://localhost:8080/` のブラウザ動作確認（SC-001〜004）・モバイル表示確認（SC-003）・404確認を実施する

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 依存なし。即時開始可能
- **Foundational (Phase 2)**: Phase 1完了後。**US1・US2の実装をブロック**
- **US1 (Phase 3)**: Phase 2完了後に開始可能
- **US2 (Phase 4)**: Phase 2完了後に開始可能（US1完了を待たなくてよいが、Controllerが同一ファイルのため実質US1後）
- **Polish (Phase 5)**: US1・US2完了後

### User Story Dependencies

- **US1 (P1)**: Phase 2完了後 → 独立テスト可能
- **US2 (P2)**: Phase 2完了後 → 独立テスト可能。T006はT004と同一ファイル（StatusController）のため実質US1後に実装

### Within Each Phase

- T002 → T003（同一ファイル。T003はT002の追記）
- T004 → T005（Controllerの戻り値型が確定してからテンプレートを作成）
- T006 → T007（同上）
- T008 と T009 は並列実行可能（別ファイル）

### Parallel Opportunities

- Phase 2内: T002とT003は同一ファイルのため**並列不可**（順次実行）
- Phase 5内: T008とT009は並列実行可能 `[P]`
- US1完了後、Controllerファイルへの追記（T006）と別テンプレート（T007）は別ファイルのため並列可

---

## Parallel Example: Phase 5

```bash
# T008・T009 は同時実行可能
Task: "app/tests/Repository/OperationStatusRepositoryTest.php を作成"
Task: "app/tests/Controller/StatusControllerTest.php を作成"
```

---

## Implementation Strategy

### MVP First（US1のみ）

1. Phase 1: Setup（T001）
2. Phase 2: Foundational（T002 → T003）
3. Phase 3: US1（T004 → T005）
4. **STOP & VALIDATE**: `http://localhost:8080/` でトップページ確認
5. SC-001〜004が満たされればMVP達成

### Incremental Delivery

1. T001〜T003: 基盤完成
2. T004〜T005: US1完成 → トップページでMVP価値提供
3. T006〜T007: US2完成 → 会社別詳細ページ追加
4. T008〜T010: テスト・最終確認

---

## Summary

| Phase | Tasks | Story | Key Output |
|---|---|---|---|
| Phase 1: Setup | T001 | - | Bootstrap 5 基盤 |
| Phase 2: Foundational | T002, T003 | - | Repositoryメソッド2本 |
| Phase 3: US1 (MVP) | T004, T005 | US1 | トップページ |
| Phase 4: US2 | T006, T007 | US2 | 会社別ページ |
| Phase 5: Polish | T008, T009, T010 | - | テスト・動作確認 |

**Total**: 10タスク | **MVP scope**: T001〜T005（5タスク）| **並列機会**: T008/T009
