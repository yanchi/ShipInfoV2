# Tasks: 便無し（no_service）ステータスの追加

**Input**: Design documents from `specs/3-no-service-status/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md

---

## Phase 1: Foundational（ブロッキング前提）

**Purpose**: Python・PHP の Enum に `no_service` を追加する。両社スクレイパーがこれを参照するため最初に完了が必要。

**⚠️ CRITICAL**: この Phase が完了するまで US1・US2 の実装を開始しないこと。

- [X] T001 [P] Python `OperationStatusEnum` に `no_service = "no_service"` を追加する (`scraper/scraper/db/models.py` の `OperationStatusEnum` クラス末尾に追記)
- [X] T002 [P] PHP `OperationStatusEnum` に `case NoService = 'no_service';` を追加する (`app/src/Enum/OperationStatusEnum.php`)

**Checkpoint**: T001・T002 完了後、`make test-scraper` が引き続き全件パスすること（既存テストへの影響がないことを確認）

---

## Phase 2: User Story 1 + 2 — 両社で便無し → `no_service` 記録（Priority: P1）

**Goal**: マルエーフェリー・マリックスライン両社のスクレイパーが便なし時に `no_service` を記録する

**Independent Test**: 両社のスクレイパーテストで「便無し → `no_service`」シナリオが通ること

### Implementation for User Story 1 + 2 (MarueFerry)

- [X] T003 [US1] `scraper/scraper/scrapers/marue_ferry.py` の `parse()` メソッドの no-service パスで `OperationStatusEnum.cancelled` を `OperationStatusEnum.no_service` に変更し、コメントも「cancelled → no_service」に更新する（`if not getattr(self, "_has_service", True):` ブロック内）
- [X] T004 [US1] `scraper/tests/test_marue_ferry.py` の `test_no_service_records_cancelled_for_both_routes` を更新する: テスト名を `test_no_service_records_no_service_for_both_routes` に変更し、アサーションを `OperationStatusEnum.no_service` に変更する

### Implementation for User Story 1 + 2 (MarixLine)

- [X] T005 [US2] `scraper/scraper/scrapers/marix_line.py` の `parse()` メソッドの末尾（既存ループの後、`self._log.info` の前）に以下のロジックを追加する: `today = date.today()` を取得し、`[down_route, up_route]` の各 route（`None` 除く）について `(route.id, today) not in seen` なら `no_service` レコードを追加する（`status_detail=None`、`valid_date=today`、`source_url=SOURCE_URL`）
- [X] T006 [US2] `scraper/tests/test_marix_line.py` の既存テスト全件を `unittest.mock.patch` で `scraper.scrapers.marix_line.date` をモックし、`date.today()` が HTML 内の日付と一致するよう固定する（`test_normal_down_delayed_up` は `date(2026, 3, 7)`、`test_both_cancelled` は `date(2026, 3, 8)`、`test_irrelevant_divs_ignored` は `date(2026, 3, 7)`、`test_date_parsed_from_info2` は `date(2026, 3, 7)`、`test_conditional_alert_is_delayed_not_cancelled` は `date(2026, 3, 7)` をモック値として使用）
- [X] T007 [US2] `scraper/tests/test_marix_line.py` に以下の2テストを追加する:
  - `test_no_service_when_no_block_for_today`: 今日の便ブロックが HTML に存在しない場合（HTML には別日のブロックのみ）、下り・上り両方のルートに `no_service`（`valid_date=today`、`status_detail=None`）が記録されることを確認する。`date.today()` を HTML 内の日付と異なる日にモックする
  - `test_no_service_only_for_missing_direction`: 今日の日付で下りブロックのみ存在し上りブロックがない場合、上りルートのみ `no_service` が追加されることを確認する

**Checkpoint**: `make test-scraper` で全テストパス確認。MarueFerry・MarixLine 両社のテストで `no_service` シナリオが通ること

---

## Phase 3: User Story 3 — 既存ステータスへの影響なし（Priority: P2）

**Goal**: `no_service` 追加後も既存ステータス（`operating`, `cancelled`, `delayed`, `suspended`）の動作が変わらないことを確認

**Independent Test**: `make test-scraper` 全件（17件以上）パス

- [X] T008 [US3] `make test-scraper` を実行し、全テストがパスすることを確認する。失敗があれば原因を修正する（Phase 2 のモック漏れ等）

**Checkpoint**: 全件パス確認

---

## Phase 4: Polish

- [X] T009 `scraper/scraper/scrapers/marue_ferry.py` のモジュール docstring（ファイル先頭）の `raw_html_hash` / `valid_date` に関する説明を `no_service` 対応を反映した内容に更新する

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1（Foundational）**: 即開始可能
- **Phase 2（US1+US2）**: Phase 1 完了後
- **Phase 3（US3）**: Phase 2 完了後
- **Phase 4（Polish）**: Phase 2 完了後（Phase 3 と並行可）

### User Story Dependencies

- **US1 (MarueFerry)** と **US2 (MarixLine)** は互いに独立して実装・テスト可能（Phase 1 完了後）
- **US3** は US1・US2 完了後の回帰確認

### Parallel Opportunities

- T001 と T002 は並行実行可（別ファイル）
- T003 と T005 は並行実行可（別ファイル、Phase 1 完了後）
- T004 と T006・T007 は並行実行可（別ファイル）

---

## Implementation Strategy

### MVP（US1 + US2 のみ）

1. Phase 1 完了（T001, T002）
2. Phase 2 完了（T003〜T007）
3. `make test-scraper` で確認
4. コミット

---

## Notes

- DBマイグレーション不要（`operation_statuses.status` は既に VARCHAR(255)）
- T006 の `date` モックには `unittest.mock.patch("scraper.scrapers.marix_line.date")` を使用し、`mock_date.today.return_value = date(2026, 3, X)` のパターンで固定する。`mock_date.side_effect = lambda *a, **kw: date(*a, **kw)` で `date(year, month, day)` の呼び出しも通すこと
- 実装の主要変更は `scraper/scraper/scrapers/marue_ferry.py` と `scraper/scraper/scrapers/marix_line.py`（テストは `scraper/tests/test_marue_ferry.py` と `scraper/tests/test_marix_line.py` も更新）
