# Tasks: マルエーフェリー情報取得方式変更

**Input**: Design documents from `specs/2-marue-fetch-update/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, quickstart.md ✅

**Organization**: US1（検索API判定）→ US2（鹿児島ページ解析）の順で実装。単一ファイル変更のため Setup/Foundational フェーズは最小限。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 並列実行可能（異なるファイル・依存なし）
- **[Story]**: 対応するユーザーストーリー（US1, US2）
- 全タスクに正確なファイルパスを記載

---

## Phase 1: Setup（既存実装の把握）

**Purpose**: 変更対象の BaseScraper インターフェースと既存コードを理解してから実装に入る

- [X] T001 `scraper/scraper/scrapers/base.py` を読み、`fetch()` → `parse()` → `save()` の呼び出しフロー・戻り値型を把握する
- [X] T002 `scraper/scraper/scrapers/marue_ferry.py` を読み、現行の URL 定数・ヘルパーメソッド一覧を把握する

---

## Phase 2: Foundational（インターフェース設計）

**Purpose**: `fetch()` と `parse()` のシグネチャを壊さずに 2 ステップ取得を実現する設計を確定する

**⚠️ CRITICAL**: Phase 1 完了後に実施。実装方針を確定してから US1/US2 へ進む

- [X] T003 `scraper/scraper/scrapers/marue_ferry.py` の先頭で `SOURCE_URL` を削除し、`SEARCH_URL = "https://www.aline-ferry.com/search/result.php"` と `KAGOSHIMA_URL = "https://www.aline-ferry.com/kagoshima/"` の 2 定数に置き換える
- [X] T004 `MarueFerry` クラスに `self._has_service: bool = True` と `self._valid_date: date` のインスタンス変数を追加する（`fetch()` → `parse()` 間の状態受け渡しに使用）

**Checkpoint**: 定数・状態変数の設計確定 → US1/US2 実装開始可能

---

## Phase 3: User Story 1 - 本日の運航有無を検索APIで確認 (Priority: P1) 🎯 MVP

**Goal**: 検索エンドポイントへのPOSTで本日便の有無を判定し、なければ `cancelled` を両ルートに保存して完了する

**Independent Test**: `make scraper-run` 後、`operation_statuses` に本日日付のマルエーフェリーレコードが存在すること。便なしの日は `cancelled` ステータスが上り・下り両方に記録されること。

### Implementation for User Story 1

- [X] T005 [US1] `scraper/scraper/scrapers/marue_ferry.py` に `_check_service(soup: BeautifulSoup) -> bool` メソッドを実装する。`BeautifulSoup` で `table.s-result tbody tr` が 1 行以上あれば `True`、なければ `False` を返す。`table.s-result` が見つからない場合は `self._log.warning("result_table_missing")` を記録して `True`（安全側）を返す
- [X] T006 [US1] `scraper/scraper/scrapers/marue_ferry.py` の `fetch()` メソッドを書き換える。`today_str = date.today().isoformat()` で `SEARCH_URL` に POST し、レスポンスを `BeautifulSoup` でパースして `_check_service(soup)` を呼び、結果を `self._has_service` に格納する。`has_service=True` なら `KAGOSHIMA_URL` を GET して HTML を返す。`has_service=False` なら空文字列 `""` を返す（`raw_html_hash` の計算対象は鹿児島ページの HTML のみ）
- [X] T007 [US1] `scraper/scraper/scrapers/marue_ferry.py` の `parse()` メソッドに、冒頭で `if not getattr(self, "_has_service", True):` を判定するブロックを追加する。`False` の場合は `_load_routes()` で上り・下り両ルートを取得し、両方に `OperationStatusEnum.cancelled`・`valid_date=date.today()`・`source_url=SEARCH_URL` のレコードを生成して返す（以降の鹿児島解析をスキップ）

**Checkpoint**: US1 完了 → `make scraper-run` で便なし日に `cancelled` が記録されることを確認可能

---

## Phase 4: User Story 2 - 鹿児島航路ページから詳細ステータスを取得 (Priority: P2)

**Goal**: 「運航あり」判定後に鹿児島航路ページを解析し、船ごとのステータステキストから `OperationStatusEnum` を決定して上り・下り両ルートに保存する

**Independent Test**: 条件付き運航日に `make scraper-run` を実行すると `operation_statuses` に `delayed` ステータスが上り・下り両方で保存されること。

### Implementation for User Story 2

- [X] T008 [US2] `scraper/scraper/scrapers/marue_ferry.py` に `_parse_status_text(text: str) -> OperationStatusEnum | None` メソッドを実装する。引数テキストに `欠航` → `cancelled`、`条件付` → `delayed`、`遅延` / `スケジュール変更` → `delayed`、`運休` → `suspended`、`通常` → `operating` を順に判定して返す。いずれも一致しない場合は `None` を返す
- [X] T009 [US2] `scraper/scraper/scrapers/marue_ferry.py` の `parse()` メソッドの `else` ブロック（`has_service=True` 時）に鹿児島ページ解析ロジックを実装する。`BeautifulSoup` で鹿児島ページの各便ブロックを表す `div.ferry-name` 要素を基点に、同一ブロック内の `div.tag-list > span` からステータステキストを取得して `_parse_status_text()` に渡し、運航ステータスを判定する。必要に応じて同一ブロック内の `div.situation-excerpt` テキストをステータス詳細として利用できるようにする。ステータスが `None`（判定不能）の場合は `self._log.warning("kagoshima_status_unknown", ship=ferry_name_div.get_text())` を記録してスキップする
- [X] T010 [US2] T009 の解析結果を `_load_routes()` の上り・下り両ルートに適用するレコード生成ロジックを `parse()` に追加する。`route_id=down_route.id` と `route_id=up_route.id` それぞれに同一の `status` / `status_detail` / `valid_date=self._valid_date` / `source_url=KAGOSHIMA_URL` を持つ辞書を生成してリストに追加する
- [X] T011 [US2] `scraper/scraper/scrapers/marue_ferry.py` から不要になった旧ヘルパーメソッド（`_parse_direction()`・`_parse_date()`・`_parse_status()`）を削除する。`_load_routes()` は再利用するため残す

**Checkpoint**: US2 完了 → `make scraper-run` で通常運航日に `operating` が上り・下り両方に記録されることを確認

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: エッジケース確認・動作検証・コード整合性チェック

- [X] T012 `scraper/scraper/scrapers/marue_ferry.py` の `parse()` 冒頭で `html` が空文字列（`has_service=False`）の際に `raw_html_hash` 計算をスキップする処理が既存 `BaseScraper` のロジックと整合しているか確認し、必要に応じて `fetch()` の戻り値を調整する
- [X] T013 [P] quickstart.md のデバッグ手順に従い `make shell-scraper` で検索エンドポイントのPOSTレスポンスを実際に確認する。`table.s-result tbody` の実際の HTML 構造が T005 の実装と一致しているか検証し、ズレがあれば T005 を修正する
- [X] T014 [P] `make scraper-run` を実行し、`operation_statuses` テーブルにマルエーフェリーのレコードが保存されることを quickstart.md の確認クエリで検証する
- [X] T015 [P] `make test-scraper` を実行し、既存のスクレイパーテストが全てパスすることを確認する

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: 依存なし。即開始可能
- **Phase 2 (Foundational)**: Phase 1 完了後
- **Phase 3 (US1)**: Phase 2 完了後
- **Phase 4 (US2)**: **Phase 3 完了後**（同一ファイルの順次実装）
- **Phase 5 (Polish)**: Phase 4 完了後

### User Story Dependencies

- **US1 (P1)**: Phase 2 完了後に開始可能
- **US2 (P2)**: **US1 完了後に開始**（US2 は `self._has_service` を前提とするため）

### Within Each User Story

- T005 → T006 → T007 の順（US1 は直列）
- T008 → T009 → T010 → T011 の順（US2 は直列）
- T013 / T014 / T015 は並列実行可能（[P]）

### Parallel Opportunities

- T001 と T002 は並列実行可能（それぞれ別ファイルの読み取り）
- T013・T014・T015 は並列実行可能

---

## Parallel Example: Phase 1

```bash
# Phase 1 の 2 タスクは並列実行可能:
Task T001: "scraper/scraper/scrapers/base.py を読む"
Task T002: "scraper/scraper/scrapers/marue_ferry.py を読む"
```

## Parallel Example: Phase 5

```bash
# Polish タスクは並列実行可能:
Task T013: "shell-scraper で POST レスポンス確認"
Task T014: "make scraper-run で DB レコード確認"
Task T015: "make test-scraper でテスト実行"
```

---

## Implementation Strategy

### MVP First (User Story 1 のみ)

1. Phase 1: Setup（コード把握）
2. Phase 2: Foundational（定数・状態変数）
3. Phase 3: US1（検索判定 + 便なし時の cancelled 保存）
4. **STOP & VALIDATE**: `make scraper-run` で便なし日の動作確認
5. US1 確認後に US2 へ進む

### Incremental Delivery

1. Phase 1 + 2 → 準備完了
2. US1 完了 → `make scraper-run` で便あり/なし判定を確認（MVP）
3. US2 完了 → 鹿児島ページのステータス解析を確認
4. Phase 5 → 動作確認・テスト通過

---

## Notes

- 実装の主要な変更は `scraper/scraper/scrapers/marue_ferry.py`（テストは `scraper/tests/test_marue_ferry.py` も更新）
- DB スキーマ変更なし
- `_load_routes()` は既存のまま再利用
- `BaseScraper` の `fetch()` / `parse()` シグネチャは変更しない
- `self._has_service` と `self._valid_date` をインスタンス変数として使用することで、`fetch()` から `parse()` へ状態を渡す
- `raw_html_hash` は鹿児島ページ HTML（または空文字列）で計算する（既存 BaseScraper のハッシュロジックに委ねる）
