# Tasks: マリックスラインの臨時便を港別ステータスに出す

**Input**: Design documents from `specs/13-marix-extra-voyages/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: 入れる。臨時便は台風のあとにしか出ず、本番で出るのを待って確かめられない。公式の保存版（2026-08〜09）を fixture にした自動テストで確かめる。テストは実装より先に書き、落ちることを確かめてから実装する。

**Story ラベル**: spec.md の User Story 番号（US1〜US5）。

**plan の Phase との対応**:

| plan | この tasks.md |
|---|---|
| A. 便の種類と、臨時便の寄る港の行 | Phase 2（T004〜T005）・Phase 3（US2）・Phase 4（US3。T010〜T011） |
| B. Base の flush と、臨時便の行の後始末 | Phase 2（T006〜T007）・Phase 4（US3。T012〜T013） |
| C. 同じキーの優先 | Phase 5（US1） |
| D. 方向 | Phase 6（US4。T019〜T020） |
| E. 航路単位 | Phase 7（US5） |
| F. トップのバッジと文書 | Phase 6（US4。T021〜T022）・Phase 8 |

US1（同じキーの優先）は US2 の臨時便の行が無いと確かめられないので、US2・US3 の後に置く。

**コミット**: 各 Phase の Checkpoint でコミットする（constitution V）。

**共通の注意**:
- DB のスキーマは変えない。マイグレーションは作らない。`BaseScraper`（`base.py`）の変更は T007 の flush の1行だけ
- `fetch()` / `parse()` / `parse_departures()` のシグネチャは変えない。`raw_html_hash`（一覧の HTML）は変えない
- 臨時便の無い日の結果は変えない（FR-013・SC-006）。既存テストの期待値を変える必要が出たら、実装を止めて理由を確かめる
- 臨時便が書いた行の目印は状態 `extra`（research R5）。URL の形（`/service/service6727/`）では見分けない（research R1）
- 本番の `SessionLocal` は `autoflush=False`。DB に書いて消す流れ（`_run_departures()` を2回以上）を確かめるテストは、最初に `db_session.autoflush = False` にする（research R10）。`conftest.py` の `db_session` は変えない
- テストの「今日」は `patch("scraper.scrapers.marix_line.date", _make_date_mock(date(...)))` で固定する（既存のテストと同じ）。出港済みかの判定（R5）に使う「今」は、`marix_line.py` で `datetime.now()` を呼ぶところを `patch("scraper.scrapers.marix_line.datetime", ...)` で固定する（`_make_date_mock` と同じ形の `_make_datetime_mock(now)` を足す）
- HTTP は `responses`（`resp_mock`）でモックする。港は `setup_port_master()`、会社は `marix_line_company` を使う
- Phase の終わりに、触った側のチェックが通ること（スクレイパー：`make test-scraper`・`make lint-scraper`、PHP：`make test-php`・`make phpstan`・`make cs-php`・`make lint-php`）

---

## Phase 1: Setup

- [X] T001 `make up` → `make test-scraper`・`make test-php` が全部通ることを確認してから始める
- [X] T002 [P] `specs/13-marix-extra-voyages/samples/` の6本を `scraper/tests/fixtures/marix/` に、quickstart.md の表の名前でコピーする（service6727 → `extra_down_20260906.html`、downstream20260906 → `down_route_change_20260906.html`、service6731 → `extra_up_20260907.html`、upstream20260907 → `up_cancel_20260907.html`、service6819 → `extra_up_naze_20260927.html`、service6664 → `extra_down_20260827.html`）
- [X] T003 `scraper/tests/test_marix_line.py` に、テスト用の道具を足す:
  - `_list_html(down: list[tuple[str, str, str]], up: list[tuple[str, str, str]]) -> str`：一覧の HTML を組み立てる。要素は（便のクラス、詳細ページの URL、info2 の文）。今の `fixtures/marix/list.html` と同じ形で、`div.service_list > div.down_stream_services` と `div.up_stream_services` の中に `div.status_single_cover {cls} > a.status_single {cls}[href] > div.info1 p.exp ＋ div.info2` を並べる
  - `_mock_extra_pages(list_html, pages: dict[str, str | int])`：一覧と、URL → fixture 名（または 500 などのステータス）を `resp_mock` に登録する
  - URL の定数：`EXTRA_DOWN_0906 = "https://marixline.com/service/service6727/"`、`DOWN_0906`・`EXTRA_UP_0907`・`UP_0907`・`EXTRA_UP_0927`・`EXTRA_DOWN_0827` も同じく
  - `_make_datetime_mock(now: datetime)`：`datetime.now()` を固定しつつ `datetime(...)` のコンストラクタも通す（`_make_date_mock` と同じ形）

**Checkpoint**: 既存テストが全部通る（コミットなし）

---

## Phase 2: Foundational（便の種類と、Base の flush）

**Purpose**: 全部の Story が使う「この便は臨時便か」の判定と、消す処理の前の flush を作る。この Phase では行の結果はまだ変えない。

### 便の種類（research R1）

- [X] T004 `scraper/tests/test_marix_line.py` に `_voyage_kind()` のテストを足す（実装の前に落ちることを確かめる）。`fetch()` を通した `MarixLine` で呼ぶ:
  - (a) 一覧の便のクラスが `temporary alert` → `"extra"`（詳細ページが 500 でも）
  - (b) 一覧の便のクラスが `route alert` で、詳細ページが `extra_down_20260906.html`（見出しに【臨時便・航行経路変更】）→ `"extra"`
  - (c) 見出しの【臨時便…】を消して、港の `temporary` だけ残した `extra_up_20260907.html` → `"extra"`
  - (d) `down_route_change_20260906.html`・`up_cancel_20260907.html`・既存の `downstream.html`・`upstream_conditional.html` → `"regular"`
  - (e) 一覧の便のクラスが `route alert` で、詳細ページが 500 → `"unknown"`（PR #89 レビュー）
  - (f) `fetch()` を通さずに（`_detail_pages` が無い）呼ぶ → `"regular"`
- [X] T005 `scraper/scraper/scrapers/marix_line.py` に `_voyage_kind(self, block: Tag, detail_html: str | None) -> str` を作る（research R1 の表）。詳細ページが取れなかったかは `getattr(self, "_detail_pages", None)` に URL があって値が None かで決める。見出しの文字はモジュールの定数 `_EXTRA_HEADING = "【臨時便"`、クラスは `_EXTRA_CLASS = "temporary"` にする。`_STATUS_BY_CLASS` に `"temporary": OperationStatusEnum.extra` を足し、上のコメント（CSS class → status mapping）に `temporary → extra（港の行だけ。航路単位には書かない）` を足す。`make test-scraper`・`make lint-scraper`

### Base の flush（research R10）

- [X] T006 `scraper/tests/test_base_departures.py` にテストを足す（実装の前に落ちることを確かめる）。`db_session.autoflush = False` にして:
  - 行 A（キー K、`source_url = U1`）を DB に書いて commit → 同じキー K で `source_url = U2` の行と、`replace_source = (route, port, U1)` の別の行（キー K'）を同じ回に `_upsert_departures()` → K の行が残る（`source_url = U2`）
- [X] T007 `scraper/scraper/scrapers/base.py` の `_upsert_departures()` で、行の書き込みのループの後、ルール5（`replace_scope`）の前に `self.session.flush()` を入れる。docstring のルール5・6の前に「消す前に flush する（本番の SessionLocal は autoflush=False。同じ回に上書きした行を、古い source_url で消さないため）」を足す。`make test-scraper`・`make lint-scraper`

**Checkpoint**: 既存テストが全部通る（結果は変わらない）＋ T004・T006 が通る → コミット

---

## Phase 3: User Story 2 - 臨時便の港が「臨時便」で出る (Priority: P1) 🎯 MVP

**Goal**: 臨時便の詳細ページで臨時便の印がある港の行を、状態「臨時便」で作る（FR-002・FR-004・FR-010）。

**Independent Test**: 9/6 の一覧（下りの欄に定期便 `route alert`＋臨時便 `temporary alert`）を読ませ、鹿児島のクロス 09:00 の行が `extra`、プラスの行が今までどおりであることを確かめる（SC-002 の前半）。

- [ ] T008 [US2] `scraper/tests/test_marix_line.py` にテストを足す（実装の前に落ちることを確かめる）。`_list_html()` で 9/6 の下りの欄に定期便（`route alert`・`DOWN_0906`）と臨時便（`temporary alert`・`EXTRA_DOWN_0906`）を置き、今日を 2026-09-06 にして `fetch()` → `parse_departures()`:
  - (a) 鹿児島・クイーンコーラルクロス・9/6 の行：`status = extra`、`scheduled_departure_at = 2026-09-06 09:00`、`scheduled_arrival_at = 2026-09-07 05:00`、`source_url = EXTRA_DOWN_0906`、`extra_voyage = True`、`replace_source` が無い
  - (b) (a) の `status_detail` に「臨時便で時間を変更し、航行経路を「鹿児島 → 那覇」に変更して運航します」が入る
  - (c) クイーンコーラルプラスの行は、臨時便を一覧から外して読んだときと同じ（名瀬・亀徳・本部が `delayed`、和泊・与論が `skipped`、出港時刻も同じ。`extra_voyage = False`）
  - (d) ログ（`structlog.testing.capture_logs()`）に `unknown_status_class`・`detail_status_unknown` が出ない
  - (e) 臨時便の詳細ページの鹿児島の港のクラスを `single firstport cancel alert` に書き換える → 鹿児島のクロスの行が `cancelled`（臨時便そのものの欠航。Edge Cases）
  - (f) 臨時便の詳細ページが 500 → 臨時便の行は0行、`extra_voyage_detail_missing` の警告が1件。予備ルートの行（船名なし）も作らない（FR-010）
  - (g) 一覧の臨時便のクラスを `route alert` にして、詳細ページが 500（種類 `unknown`）→ 今までどおり予備ルートの行（船名なし・`delayed`・`source_url = EXTRA_DOWN_0906`）が5港にできる（R6）
- [ ] T009 [US2] `scraper/scraper/scrapers/marix_line.py` の `parse_departures()` を直す:
  - ブロックごとに `kind = self._voyage_kind(block, detail_html)` を決める
  - `kind == "extra"` なら、一覧のクラスに関係なく便全体の状態を `OperationStatusEnum.extra` として `_departures_from_detail()` に渡す（research R3）。詳細ページが無い・読めないときは、予備ルートに行かずに `extra_voyage_detail_missing`（url・route_id）を出して次のブロックへ（research R6）。読めたら URL を `self._read_extra_urls` に足す（`parse_departures()` の頭で空の set にする）
  - `kind == "unknown"` は今までどおり（予備ルート）
  - `_departures_from_detail()` の作る行に `extra_voyage: bool`（`voyage_status == OperationStatusEnum.extra`）を足す。臨時便の行には `replace_source` を付けない（research R7）
  - `make test-scraper`・`make lint-scraper`

**Checkpoint**: T008 が通る・既存テストが全部通る → コミット

---

## Phase 4: User Story 3 - 臨時便が寄らない港に、臨時便の行を作らない (Priority: P1)

**Goal**: 臨時便の詳細ページで「寄港しません」の港には、臨時便からの行を作らない（FR-003）。寄らなくなった港・出港日がずれた日・分からなかった回の予備ルートの、臨時便の古い行を消す（FR-011）。

**Independent Test**: 9/6・9/27 の臨時便を読ませ、寄らない港の臨時便の行が0行であることを確かめる（SC-002 の後半・SC-003 の後半）。

### 寄らない港（research R3）

- [ ] T010 [US3] `scraper/tests/test_marix_line.py` にテストを足す（実装の前に落ちることを確かめる）:
  - (a) T008 と同じ 9/6 の一覧で、クイーンコーラルクロスの名瀬・亀徳・和泊・与論・本部の行が0行（`skipped` の行も無い）
  - (b) 9/27 の臨時便（`extra_up_naze_20260927.html`。上りの欄・`temporary alert`・info2 は「2026年9月27日 那覇港発 2026年9月27日 鹿児島新港 向け」にして、方向は今の判定で決まるようにする。名瀬発は US4 で確かめる）を今日 2026-09-27 で読む → 8/25 の行（2026・2027 とも）が0行。那覇・本部・与論・和泊・亀徳の行が0行
  - (c) (a) で、定期便（プラス）の和泊・与論の `skipped` は今までどおりある（定期便の `no_status` は変えない）
- [ ] T011 [US3] `marix_line.py` の `_departures_from_detail()` で、`voyage_status == OperationStatusEnum.extra` のときは `no_status` の港を `by_port` に入れない（時刻も読まない）。寄港順の港が `by_port` に無いときの `detail_stop_missing` の警告は、臨時便では出さない（research R3）。引数は増やさない（PR #89 レビュー）。`make test-scraper`・`make lint-scraper`

### 後始末（research R7）

- [ ] T012 [US3] `scraper/tests/test_marix_line.py` にテストを足す（実装の前に落ちることを確かめる）。全部 `db_session.autoflush = False` にして `_run_departures()` を2回:
  - (a) US3-3：1回目は 9/6 の臨時便の詳細ページの名瀬を `single temporary alert`（入港 9/6 20:00・出港 20:50）に書き換えて読む → 名瀬・クロスの `extra` の行ができる。2回目は元の `extra_down_20260906.html`（名瀬は `no_status`）→ 名瀬・クロスの行が消える。鹿児島の行は残る
  - (b) 1回目は元の 9/6 の臨時便、2回目は鹿児島の出港を「09月07日 09:00」に書き換えて読む → 9/6 の鹿児島・クロスの行が消え、9/7 の行ができる
  - (c) 1回目は一覧の臨時便のクラスを `route alert`・詳細ページ 500（種類 `unknown`。予備ルートの行が5港にできる）、2回目は `temporary alert`・詳細ページあり → 船名なしで `source_url = EXTRA_DOWN_0906` の行が全部消え、鹿児島・クロスの `extra` の行だけになる
  - (d) 2回目に臨時便の詳細ページが 500 → 1回目の行は全部残る（読めなかった回は消さない）
  - (e) 1回目に定期便（プラス）の行もある状態で (a) を流す → プラスの行は変わらない（`source_url` が違うので消えない）
- [ ] T013 [US3] `marix_line.py` に `_upsert_departures(self, records)` を作る（Base を上書き）。`created, updated = super()._upsert_departures(records)` → `self.session.flush()` → `self._read_extra_urls` の URL ごとに、`DepartureStatus.source_url == url` の行のうち、`records` の中で `extra_voyage` かつ `source_url == url` の行のキー `(route_id, port_id, departure_date, ship_name)` に無い行を消す（`session.delete()`）。戻り値は Base のまま（research R7）。`parse_departures()` を通らずに呼ばれたとき（`_read_extra_urls` が無い）は何もしない。`make test-scraper`・`make lint-scraper`

**Checkpoint**: T010・T012 が通る・既存テストが全部通る → コミット

---

## Phase 5: User Story 1 - 欠航の定期便を置き換えた臨時便が出る (Priority: P1)

**Goal**: 同じキー（航路・港・出港日・船）に定期便と臨時便が来たら、一覧の並び順に関係なく臨時便を優先する。前の回の臨時便の行は、詳細ページが取れない回と出港済みのときだけ守る（FR-005〜FR-007）。予備ルートは今までどおり（FR-015）。

**Independent Test**: 9/7 の一覧（上りの欄に定期便 `cancel alert`・臨時便 `temporary alert`）を2通りの並び順で読ませ、那覇・名瀬のクロスが `extra`、本部・与論・和泊・亀徳のクロスが `cancelled` であることを確かめる（SC-001）。

### 同じ回の優先（research R4）

- [ ] T014 [US1] `scraper/tests/test_marix_line.py` にテストを足す（実装の前に落ちることを確かめる）。今日 2026-09-07、`@pytest.mark.parametrize("extra_first", [True, False])` で一覧の並び順を入れ替える:
  - (a) `parse_departures()` の結果で、上り・クロス・9/7 の那覇（07:00）・名瀬（21:20）がそれぞれ1行で `extra`、`source_url = EXTRA_UP_0907`
  - (b) 同じく本部・与論・和泊・亀徳のクロスが1行ずつで `cancelled`、`source_url = UP_0907`
  - (c) 同じキーの行が2本無い（`(route_id, port_id, departure_date, ship_name)` が重複しない）。`departure_duplicate_key` の警告が出ない
  - (d) `db_session.autoflush = False` にして `_run_departures()` で DB に書いた後も (a)(b) のとおり（1キー1行）
  - (e) 定期便が走るとき（FR-006）：`up_cancel_20260907.html` の港のクラスを全部 `normal` に、h1 の【欠航】を【通常運航】にした定期便と、9/7 の臨時便を読む → 那覇・クロスの行は定期便（`operating`、`source_url = UP_0907`）。`status_detail` の終わりに「（臨時便 07:00発あり）」、`extra_voyage_conflict` の警告が1件
- [ ] T015 [US1] `marix_line.py` に `_resolve_extra_conflicts(self, records, kept, list_urls, read_extra_urls) -> list[dict]` を作り、`parse_departures()` の最後（`parsed_departures` のログの前）で呼ぶ（research R4。`kept`・`list_urls` は T017 で使う。ここでは空で渡してよい）:
  - 同じキーの行を、臨時便（`extra_voyage`）と定期便に分ける
  - 定期便の状態が `cancelled`・`suspended`・`skipped`・`unknown` → 臨時便の行を残す
  - それ以外 → 定期便の行を残し、`status_detail` の終わりに `（臨時便 HH:MM発あり）`（臨時便の出港時刻）を足して `extra_voyage_conflict`（キー・両方の URL）を出す
  - 臨時便同士・定期便同士の重複は触らない（Base が先の行を使う）
  - 返す行の順番は元の順を保つ
  - 落とした定期便の行は `self._dropped_regular` にためる。T013 の `_upsert_departures()` の後始末に、落とした行の `replace_source` ごとに「その `(route_id, port_id, source_url)` の行のうち、同じ `replace_source` の定期便の行（落とした行も含む）の `(departure_date, ship_name)` に無い行を消す」を足す（research R7。落とした行は Base の `replace_source` に届かないため）
  - `make test-scraper`・`make lint-scraper`

### 前の回の行（research R5）

- [ ] T016 [US1] `scraper/tests/test_marix_line.py` にテストを足す（実装の前に落ちることを確かめる）。全部 `db_session.autoflush = False`、1回目は今日 2026-09-07・今 2026-09-07 06:00 で、9/7 の一覧（定期便＋臨時便）を `_run_departures()`:
  - (a) US1-4：2回目は今 06:30、臨時便を一覧に残したまま詳細ページを 500 → 那覇・名瀬のクロスは `extra` のまま
  - (b) US1-5：2回目は今 08:00（那覇 07:00 は出港済み、名瀬 21:20 はまだ）、臨時便を一覧から外す → 那覇・名瀬のクロスは両方 `extra` のまま（出港済みは便ごと。analyze M1）
  - (c) US1-6：2回目は今 06:30（未出港）、臨時便を一覧から外す → 那覇・名瀬のクロスは `cancelled`（`source_url = UP_0907`）
  - (d) 2回目は今 06:30、臨時便の詳細ページの那覇・名瀬の日付を「09月08日」に書き換える → 9/7 の那覇・名瀬のクロスは `cancelled`（`source_url = UP_0907`）に戻り、9/8 に `extra` の行がある（R5・R7。flush が無いと 9/7 の行が消えるので、T007 の確認にもなる）
  - (e) 2回目は今 06:30、定期便を全部 `normal` に書き換え、臨時便を一覧から外す → 那覇のクロスは `operating`（定期便が走るときはいつでも定期便）
  - (f) 日をまたぐ臨時便（PR #89 レビュー）：1回目の臨時便の詳細ページの那覇を「09月06日」23:00 発に書き換える（名瀬は 9/7 21:20 のまま）。2回目は今日 2026-09-07・今 08:00、臨時便を一覧から外す（一覧の便の始発日は 9/7 だけ）→ 名瀬のクロスは `extra` のまま（始発港の 9/6 23:00 で出港済み）。範囲の中だけで取ると名瀬 21:20 で「未出港」になり `cancelled` に戻るので、これで落ちることを確かめる
- [ ] T017 [US1] `marix_line.py` を直す（research R5）:
  - `_extra_rows_kept(self, route_ids: list[int], since: date) -> dict[tuple, str]`：`status = 'extra'` で `departure_date >= since` の行の、キー → `source_url`。`parse_departures()` の頭で1回だけ呼ぶ。`since` は一覧の便の始発日（`_parse_date()`）のいちばん前、一覧に便が無ければ今日
  - `_extra_first_departures(self, route_ids: list[int], urls: set[str]) -> dict[str, datetime | None]`：`status = 'extra'` で `source_url IN urls` の行を `GROUP BY source_url` して `MIN(scheduled_departure_at)`。出港日の範囲で絞らない（日をまたぐ便の始発港の行を拾うため。research R5）。`urls` は `_extra_rows_kept()` の値。空なら DB を読まない
  - `list_urls`：今回の一覧の便の URL 全部
  - `_resolve_extra_conflicts()` で、臨時便の行が無いキーの定期便の行（状態が `cancelled`・`suspended`・`skipped`・`unknown`）について、`kept` にそのキーがあり、次のどちらかなら定期便の行を落とす：① `source_url` が `list_urls` にあって `read_extra_urls` に無い、② その `source_url` の `_extra_first_departures()` の値（始発港の出港）が今（`datetime.now()`）以前。②は港の行ごとに見ない
  - `make test-scraper`・`make lint-scraper`

### 予備ルート（research R6・FR-015）

- [ ] T018 [US1] `scraper/tests/test_marix_line.py` にテストを足す。今日 2026-09-06、9/6 の一覧（定期便＋臨時便）で定期便（プラス）の詳細ページを 500 → `parse_departures()` の結果に、鹿児島 9/6 のプラスの予備ルートの行（船名なし・`delayed`）と、クロスの `extra` の行が両方ある（SC-008 の前半）。もう1つ、9/7 の一覧で定期便の詳細ページを 500 → 1回目、詳細ページあり → 2回目（`autoflush = False`・`_run_departures()`）で、那覇・名瀬はクロスの `extra` の1行だけ（SC-008 の後半。2回目の那覇・名瀬の定期便の行は臨時便に負けて落ちるので、船名なしの行は T015 の「落とした行の `replace_source`」で消える）。前半は今の作りで通るはず。落ちたら実装を止めて理由を確かめる

**Checkpoint**: T014・T016・T018 が通る・既存テストが全部通る → コミット

---

## Phase 6: User Story 4 - 途中の港から出る臨時便が出る (Priority: P2)

**Goal**: 名瀬発などの臨時便の方向を、一覧の欄・行き先から決める（FR-009）。トップで、臨時便以外の行が無い日のバッジを「臨時便」にする（FR-014）。

**Independent Test**: 9/27 の臨時便（名瀬港発 鹿児島新港向け）を上りの欄に置いて読ませ、上りの名瀬（9/27 05:50）が `extra` であることを確かめる（SC-003）。

### 方向（research R2）

- [ ] T019 [P] [US4] `scraper/tests/test_marix_line.py` にテストを足す（実装の前に落ちることを確かめる）:
  - (a) 上りの欄に `temporary alert`・`EXTRA_UP_0927`・info2「2026年9月27日 名瀬港発 2026年9月27日 鹿児島新港 向け」、今日 2026-09-27 → 上りの航路に名瀬・クロス・9/27 05:50 の `extra` の行。鹿児島の行は無い。`direction_unknown` が出ない
  - (b) 同じ便を、欄の無い一覧（`<html><body>` の直下に `div.status_single_cover`）に置く → 行き先「鹿児島新港 向け」で上り。結果は (a) と同じ
  - (c) 欄も無く、info2 が「2026年9月27日 名瀬港発」だけ → `direction_unknown` を出して読み飛ばす（今のまま）
  - (d) 既存の `HTML_NORMAL_DOWN_DELAYED_UP` などの結果が変わらない（既存テストがそのまま通ることで確かめる）
- [ ] T020 [US4] `marix_line.py` の `_parse_direction(self, info2_text: str, block: Tag | None = None) -> str | None` を直す（research R2）：今の始発港 → `block` の祖先の `div.down_stream_services`（下り）・`div.up_stream_services`（上り）→ 行き先（`那覇\S*\s*向け` → 下り、`鹿児島\S*\s*向け` → 上り）の順。`parse()`・`parse_departures()` から `block` を渡す。`make test-scraper`・`make lint-scraper`

### トップのバッジ（research R9、contracts/ui-status.md）

- [ ] T021 [P] [US4] テストを足す（実装の前に落ちることを確かめる）:
  - `app/tests/View/PortBoardDayTest.php`：`hasRegularDeparturesOf()` が、始発港の行も含めて Extra 以外の出発の entry があれば true、Extra だけ・何も無ければ false、ほかの会社・方向は見ない
  - `app/tests/Controller/StatusControllerTest.php`。既存の `testIndexCardMidwayExtraOnlyShowsExtraBadge()` と同じ道具（`createPortBoardData()`・`updateTestDeparture()`・`setRouteStatus()`・`findCard()`）を使う:
    - (a) `testIndexCardOriginExtraOnlyShowsExtraBadge`：航路が `NoService`、今日の便が始発港の Extra だけ（`createPortBoardData()` の後、途中の港の行を消す）→ バッジが「◆ 臨時便」、`.route-extra` が「◆ 臨時便 〇〇 HH:MM発」、「便なし」が出ない（SC-007）
    - (b) `testIndexCardOriginExtraWithOriginRegularKeepsNoService`：航路が `NoService`、始発港に Extra と、状態が不明の定期便の行（船名なし）→ 今までどおり「— 便なし」（PR #89 レビュー）
    - (c) `testIndexCardOriginExtraWithMidwayRegularKeepsRegularBadge`：始発港が Extra、途中の港に定期便の通常運航 → 今までどおり定期便のバッジ（通常運航）
    - (d) 航路が欠航で始発港が Extra → バッジは欠航のまま（既存の `testIndexCardShowsExtraDepartureUnderRouteBadge` と同じ結果を確かめる）
- [ ] T022 [US4] `app/src/View/PortBoardDay.php` に `hasRegularDeparturesOf(int $companyId, RouteDirectionEnum $direction): bool` を足す（全部の行のうち、その会社・方向で `isDeparture()` かつ状態が Extra でない entry があるか）。`app/src/Controller/StatusController.php` の `routesDepartingMidway()` で、`!$today->hasRegularDeparturesOf(...)` かつ `$today->firstExtraDepartureOf(...) !== null` なら `['kind' => 'badge', 'state' => null, 'status' => OperationStatusEnum::Extra]`、それ以外は今までどおり `midwayDisplay()`。メソッドの docblock に「臨時便以外の行が無く、臨時便があれば「臨時便」（13-marix-extra-voyages FR-014）」を足す。`make test-php`・`make phpstan`・`make cs-php`

**Checkpoint**: T019・T021 が通る・既存テストが全部通る → コミット

---

## Phase 7: User Story 5 - トップのバッジは定期便で決まる (Priority: P2)

**Goal**: 航路単位（航路×日付）は定期便だけで決める。並び順で「不明」にならない。分からない便で「便なし」にしない（FR-008）。

**Independent Test**: 9/6・9/7 の一覧を2通りの並び順で `parse()` させ、航路単位が 9/6 下り `delayed`、9/7 上り `cancelled` であることを確かめる（SC-004）。

- [ ] T023 [P] [US5] `scraper/tests/test_marix_line.py` にテストを足す（実装の前に落ちることを確かめる）。`fetch()` → `parse()`:
  - (a) `@pytest.mark.parametrize("extra_first", [True, False])`、今日 2026-09-06、9/6 下りの欄に定期便（`route alert`）と臨時便（`temporary alert`）→ 下り 9/6 が `delayed`。`unknown` の行が無い。`unknown_status_class` が出ない
  - (b) 同じく今日 2026-09-07、9/7 上りの欄に定期便（`cancel alert`）と臨時便 → 上り 9/7 が `cancelled`
  - (c) 今日 2026-09-27、上りの欄に 9/27 の臨時便だけ → 上り 9/27 は `no_service`（`extra` の行を返さない）
  - (d) (a) で、一覧の臨時便のクラスを `route alert` にして（一覧に temporary が無い場合。research R1）、詳細ページで臨時便とわかる → 結果は (a) と同じ
  - (e) `parse()` の結果に `status = extra` の行が1つも無い（`operation_statuses` の ENUM に無いため）
  - (f) SC-009：今日 2026-09-07、上りの欄に便を1つだけ、一覧のクラス `foo alert`（状態として読めず temporary も無い）・詳細ページ 500 で置く → 上り 9/7 の行が無い（`unknown` も `no_service` も無い）。`voyage_kind_unknown` の警告が1件
  - (g) 今日 2026-09-07、上りの欄に便を1つだけ、一覧のクラス `route alert`・詳細ページ 500 で置く → 上り 9/7 は今までどおり `delayed`（控えの行）
  - (h) 今日 2026-09-07、上りの欄に `route alert`・詳細ページ 500 の便を先、定期便（`cancel alert`・詳細ページあり）を後に置く → 上り 9/7 が `cancelled`（定期便が控えの行に勝つ）。(f) の便を先にしても同じ
  - (i) 既存の `test_unknown_class_voyage_is_unknown_not_cancelled`（一覧のクラスは読めないが、詳細ページは取れて定期便とわかる）は今までどおり `unknown`
  - (j) 既存の航路単位のテスト（`test_normal_down_delayed_up`・`test_both_cancelled`・`test_no_service_*` など。詳細ページをモックしていないので種類は `unknown`）が、期待値を変えずに全部通る（analyze H1）
- [ ] T024 [US5] `marix_line.py` の `parse()` を直す（research R8）:
  - ブロックごとに `kind = self._voyage_kind(block, detail_html)`（`detail_html` は `getattr(self, "_detail_pages", {}).get(urljoin(SOURCE_URL, href))`）
  - `extra` → 行を作らず、`seen` にも入れずに次へ
  - `unknown` で一覧のクラスが状態として読める → 今までどおりの行（一覧のクラスの状態・詳細）を作るが、`records` には入れず `fallback_records`（控えの行）にためて次へ。`seen` にも入れない
  - `unknown` で一覧のクラスが読めない → `voyage_kind_unknown`（url）を出し、行を作らず、キー `(route.id, valid_date)` を `unknown_keys` にためて次へ
  - ループの後、`no_service` を書く前に：`fallback_records` を一覧の順に見て、キーが `seen` に無ければ `records` に足して `seen` に入れる。そのあと `seen |= unknown_keys`
  - `make test-scraper`・`make lint-scraper`

**Checkpoint**: T023 が通る・既存テストが全部通る → コミット

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T025 [P] `scraper/scraper/scrapers/marix_line.py` 冒頭の docstring を書き足す：CSS class の対応に `temporary → extra`、便の種類（R1）、方向の決め方（R2）、寄らない港は作らないこと（R3）、同じキーの優先と前の回の行（R4・R5）、臨時便に予備ルートを使わないこと（R6）、後始末（R7）、航路単位（R8）。確認日と例（2026-09-06 service6727・2026-09-07 service6731・2026-09-27 service6819）
- [ ] T026 [P] `specs/12-marue-extra-voyages/contracts/ui-status.md` の「出るところ」の `midwayDisplay()` の段落の後に「臨時便以外の行が無い日のバッジは specs/13-marix-extra-voyages/contracts/ui-status.md」と1行足す
- [ ] T027 SC-005 をマリックスのデータで確かめる。今日を 2026-09-07 にした `scraper/tests/test_marix_line.py` のテストで、9/7 の一覧（定期便＋臨時便）を `run()` で DB に書き、上り 9/7 の航路単位が `cancelled`、那覇・名瀬のクロスが `extra` であることを確かめる。画面と通知は、同じ形の行を `app/tests/Controller/StatusControllerTest.php`（航路が欠航・始発港が Extra →「✗ 欠航」と「◆ 臨時便 那覇 07:00発」）と `app/tests/Service/IrregularStatusMailerTest.php`（欠航の航路に Extra の港 → 本文に「- 那覇 07:00発 クイーンコーラルクロス：臨時便」、状況は「欠航」）で確かめる。12 の既存テストで同じ形がもう確かめられていれば、そのテスト名を quickstart.md に書いて足さない
- [ ] T028 全部のチェックを流す：`make test-scraper`・`make lint-scraper`・`make test-php`・`make phpstan`・`make cs-php`・`make lint-php`・`make check-schema`・`make verify-prod`
- [ ] T029 `make up` → `make scraper-run` で、今の公式の一覧（臨時便なし）でエラー・新しい警告が出ないこと、`/ports`・トップが今と同じことを目で見る。`make notify-dry-run` で本文が崩れないこと。臨時便が出ていない日なので、臨時便の表示は T021・T027 の画面のテストと 12 の既存テストで代える
- [ ] T030 quickstart.md の本番の確認手順を、実装に合わせて直す（ログのイベント名 `extra_voyage_detail_missing`・`extra_voyage_conflict`・`voyage_kind_unknown`、SQL）

**Checkpoint**: 全部通る → コミット → PR

---

## Dependencies & Execution Order

```
Phase 1 → Phase 2 → Phase 3 (US2) → Phase 4 (US3) → Phase 5 (US1)
                 ├→ Phase 6 (US4)  ※ T019〜T020 は Phase 3 の臨時便の行に依存。T021〜T022（PHP）は Phase 1 だけに依存
                 └→ Phase 7 (US5)  ※ Phase 2 の便の種類だけに依存
Phase 3〜7 → Phase 8
```

- Phase 2 の `_voyage_kind()` が全部のスクレイパーの Story の前提。T007 の flush は、DB に書いて消す流れのテスト（T012・T014(d)・T016・T018）の前提
- US3 の後始末（T013）は US2 の `_read_extra_urls`（T009）を使う
- US1 は US2 の臨時便の行（T009）と US3 の寄らない港の扱い（T011）・後始末（T013）の上に乗る
- US5（`parse()`）と US2〜US1（`parse_departures()`）は別の関数で、並べられる
- PHP（T021〜T022）はスクレイパーと独立

## Parallel Examples

- Phase 1：T002（fixture）と T003（テスト用の道具）は別の作業
- Phase 2：T004〜T005（`marix_line.py`）と T006〜T007（`base.py`）は別のファイル
- Phase 6 と Phase 7：T021・T022（PHP）と T023・T024（`parse()`）は別のファイル・関数
- Phase 8：T025（docstring）と T026（12 の契約）

## Implementation Strategy

- **MVP**：Phase 1〜5（US2・US3・US1）。臨時便が寄る港に「臨時便」が出て、寄らない港に変な行が出ず、9/7 のような「欠航した便の代わりの臨時便」が並び順に関係なく出る
- **次**：Phase 7（US5）で、トップのバッジが並び順で「不明」になるのを直す。MVP と一緒に出すのが望ましい（9/6・9/7 のどちらも、臨時便が一覧で先だとトップが「不明」になるため）
- **最後**：Phase 6（US4）で名瀬発の臨時便とトップのバッジ。名瀬発は出る回数が少ない
- PR は1つ・デプロイは1回。スキーマの変更も新しい状態も無いので、スクレイパーと Web の順番は問わない（research R11）
