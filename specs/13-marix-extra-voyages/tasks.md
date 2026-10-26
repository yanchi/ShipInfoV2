# Tasks: マリックスラインの臨時便を港別ステータスに出す

**Input**: Design documents from `specs/13-marix-extra-voyages/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: 入れる。臨時便は台風のあとにしか出ず、本番で出るのを待って確かめられない。公式の保存版（2026-08〜09）を fixture にした自動テストで確かめる。テストは実装より先に書き、落ちることを確かめてから実装する。

**Story ラベル**: spec.md の User Story 番号（US1〜US5）。

**plan の Phase との対応**:

| plan | この tasks.md |
|---|---|
| A. 臨時便を見分けて、寄る港の行を作る | Phase 2（T004〜T005）・Phase 3（US2）・Phase 4（US3） |
| B. 方向と航路単位 | Phase 6（US4）・Phase 7（US5） |
| C. 同じキーの優先 | Phase 5（US1。T010〜T014） |
| D. 予備ルート | Phase 5（US1。T015〜T016） |
| E. トップのバッジと文書 | Phase 6（US4。T019〜T020）・Phase 8 |

US1（同じキーの優先）は US2 の臨時便の行が無いと確かめられないので、US2・US3 の後に置く。

**コミット**: 各 Phase の Checkpoint でコミットする（constitution V）。

**共通の注意**:
- DB のスキーマは変えない。マイグレーションは作らない。`BaseScraper`（`base.py`）は変えない
- `fetch()` / `parse()` / `parse_departures()` のシグネチャは変えない。`raw_html_hash`（一覧の HTML）は変えない
- 臨時便の無い日の結果は変えない（FR-013・SC-006）。既存テストの期待値を変える必要が出たら、実装を止めて理由を確かめる
- 臨時便が書いた行の目印は状態 `extra`（research R5）。URL の形（`/service/service6727/`）では見分けない（research R1）
- テストの「今日」は `patch("scraper.scrapers.marix_line.date", _make_date_mock(date(...)))` で固定する（既存のテストと同じ）
- HTTP は `responses`（`resp_mock`）でモックする。港は `setup_port_master()`、会社は `marix_line_company` を使う
- Phase の終わりに、触った側のチェックが通ること（スクレイパー：`make test-scraper`・`make lint-scraper`、PHP：`make test-php`・`make phpstan`・`make cs-php`・`make lint-php`）

---

## Phase 1: Setup

- [ ] T001 `make up` → `make test-scraper`・`make test-php` が全部通ることを確認してから始める
- [ ] T002 [P] `specs/13-marix-extra-voyages/samples/` の6本を `scraper/tests/fixtures/marix/` に、quickstart.md の表の名前でコピーする（service6727 → `extra_down_20260906.html`、downstream20260906 → `down_route_change_20260906.html`、service6731 → `extra_up_20260907.html`、upstream20260907 → `up_cancel_20260907.html`、service6819 → `extra_up_naze_20260927.html`、service6664 → `extra_down_20260827.html`）。コピーの後 `cmp` で同じ中身を確かめる
- [ ] T003 `scraper/tests/test_marix_line.py` に、一覧の HTML を組み立てるテスト用の関数 `_list_html(down: list[tuple[str, str, str]], up: list[tuple[str, str, str]]) -> str` を足す。要素は（便のクラス、詳細ページの URL、info2 の文）。今の `fixtures/marix/list.html` と同じ形で、`div.service_list > div.down_stream_services` と `div.up_stream_services` の中に `div.status_single_cover {cls} > a.status_single {cls}[href] > div.info1 p.exp ＋ div.info2` を並べる。あわせて、URL と fixture 名の対応から `resp_mock` を登録する `_mock_extra_pages(list_html, pages: dict[str, str])` も足す（URL の定数：`EXTRA_DOWN_0906 = "https://marixline.com/service/service6727/"`、`DOWN_0906`・`EXTRA_UP_0907`・`UP_0907`・`EXTRA_UP_0927`・`EXTRA_DOWN_0827` も同じく）

**Checkpoint**: 既存テストが全部通る（コミットなし）

---

## Phase 2: Foundational（臨時便を見分ける）

**Purpose**: 全部の Story が使う「この便は臨時便か」の判定を作る。この Phase では行の結果はまだ変えない。

- [ ] T004 `scraper/tests/test_marix_line.py` に `_is_extra_voyage()` のテストを足す（実装の前に落ちることを確かめる）:
  - (a) 一覧の便のクラスが `temporary alert` → True（詳細ページなしでも）
  - (b) 一覧の便のクラスが `route alert`（クラスに temporary なし）でも、詳細ページが `extra_down_20260906.html`（見出しに【臨時便・航行経路変更】）→ True
  - (c) 見出しの【臨時便…】を消して、港の `temporary` だけ残した `extra_up_20260907.html` → True
  - (d) `down_route_change_20260906.html`・`up_cancel_20260907.html`・既存の `downstream.html`・`upstream_conditional.html` → False
  - (e) 詳細ページが None で、一覧のクラスに temporary が無い → False
- [ ] T005 `scraper/scraper/scrapers/marix_line.py` に `_is_extra_voyage(self, block: Tag, detail_html: str | None) -> bool` を作る（research R1）。一覧の便のクラスに `temporary`、詳細ページの `h1.heading1` に `【臨時便`、`div.service > div.single` のどれかのクラスに `temporary`、のどれか。見出しの文字はモジュールの定数 `_EXTRA_HEADING = "【臨時便"`、クラスは `_EXTRA_CLASS = "temporary"` にする。`_STATUS_BY_CLASS` に `"temporary": OperationStatusEnum.extra` を足し、上のコメント（CSS class → status mapping）に `temporary → extra（港の行だけ。航路単位には書かない）` を足す。`make test-scraper`・`make lint-scraper`

**Checkpoint**: 既存テストが全部通る（結果は変わらない）＋ T004 が通る → コミット

---

## Phase 3: User Story 2 - 臨時便の港が「臨時便」で出る (Priority: P1) 🎯 MVP

**Goal**: 臨時便の詳細ページで臨時便の印がある港の行を、状態「臨時便」で作る（FR-002・FR-004・FR-010・FR-011）。

**Independent Test**: 9/6 の一覧（下りの欄に定期便 `route alert`＋臨時便 `temporary alert`）を読ませ、鹿児島のクロス 09:00 の行が `extra`、プラスの行が今までどおりであることを確かめる（SC-002 の前半）。

- [ ] T006 [US2] `scraper/tests/test_marix_line.py` にテストを足す（実装の前に落ちることを確かめる）。`_list_html()` で 9/6 の下りの欄に定期便（`route alert`・`DOWN_0906`）と臨時便（`temporary alert`・`EXTRA_DOWN_0906`）を置き、今日を 2026-09-06 にして `fetch()` → `parse_departures()`:
  - (a) 鹿児島・クイーンコーラルクロス・9/6 の行：`status = extra`、`scheduled_departure_at = 2026-09-06 09:00`、`scheduled_arrival_at = 2026-09-07 05:00`、`source_url = EXTRA_DOWN_0906`、`replace_source = (下りの route_id, 鹿児島の port_id, EXTRA_DOWN_0906)`、`extra_voyage = True`
  - (b) (a) の `status_detail` に「臨時便で時間を変更し、航行経路を「鹿児島 → 那覇」に変更して運航します」が入る
  - (c) クイーンコーラルプラスの行は、臨時便を一覧から外して読んだときと同じ（名瀬・亀徳・本部が `delayed`、和泊・与論が `skipped`、出港時刻も同じ）
  - (d) ログ（`structlog.testing.capture_logs()`）に `unknown_status_class`・`detail_status_unknown` が出ない
  - (e) 臨時便の詳細ページの鹿児島の港のクラスを `single firstport cancel alert` に書き換える → 鹿児島のクロスの行が `cancelled`（臨時便そのものの欠航。Edge Cases）
  - (f) 臨時便の詳細ページが 500 → 臨時便の行は0行、`extra_voyage_detail_missing` の警告が1件。予備ルートの行（船名なし）も作らない（FR-010）
  - (g) 前の回に (a) の行を DB に書いた（`_run_departures()`）後、臨時便の詳細ページで鹿児島の出港を「09月07日 09:00」に書き換えて読む → 9/6 の行は消え、9/7 の行ができる（FR-011。`_run_departures()` を2回）
- [ ] T007 [US2] `scraper/scraper/scrapers/marix_line.py` の `parse_departures()` を直す:
  - ブロックごとに `extra = self._is_extra_voyage(block, detail_html)` を決める
  - `extra` なら、便全体の状態を `OperationStatusEnum.extra` として `_departures_from_detail()` に渡す（見出しの h2 を詳細に入れるため。research R3）。詳細ページが無い・読めないときは、予備ルートに行かずに `extra_voyage_detail_missing`（url・route_id）を出して次のブロックへ（research R6）
  - `_departures_from_detail()` の作る行に `extra_voyage: bool` を足す（定期便は False）。`replace_source` は今のまま（臨時便の URL になる）
  - `make test-scraper`・`make lint-scraper`

**Checkpoint**: T006 が通る・既存テストが全部通る → コミット

---

## Phase 4: User Story 3 - 臨時便が寄らない港に、臨時便の行を作らない (Priority: P1)

**Goal**: 臨時便の詳細ページで「寄港しません」の港には、臨時便からの行を作らない（FR-003）。

**Independent Test**: 9/6・9/27 の臨時便を読ませ、寄らない港の臨時便の行が0行であることを確かめる（SC-002 の後半・SC-003 の後半）。

- [ ] T008 [US3] `scraper/tests/test_marix_line.py` にテストを足す（実装の前に落ちることを確かめる）:
  - (a) T006 と同じ 9/6 の一覧で、クイーンコーラルクロスの名瀬・亀徳・和泊・与論・本部の行が0行（`skipped` の行も無い）
  - (b) 9/27 の臨時便（`extra_up_naze_20260927.html`。上りの欄・`temporary alert`・info2 は「2026年9月27日 那覇港発 2026年9月27日 鹿児島新港 向け」にして、方向は今の判定で決まるようにする。名瀬発は US4 で確かめる）を今日 2026-09-27 で読む → 8/25 の行（2026・2027 とも）が0行。那覇・本部・与論・和泊・亀徳の行が0行
  - (c) (a) で、定期便（プラス）の和泊・与論の `skipped` は今までどおりある（定期便の `no_status` は変えない）
- [ ] T009 [US3] `marix_line.py` の `_departures_from_detail()` に引数 `extra: bool` を足す。`extra` のときは `no_status` の港を `by_port` に入れない（時刻も読まない）。寄港順の港が `by_port` に無いときの `detail_stop_missing` の警告は、`extra` のときは出さない（research R3）。`make test-scraper`・`make lint-scraper`

**Checkpoint**: T008 が通る・既存テストが全部通る → コミット

---

## Phase 5: User Story 1 - 欠航の定期便を置き換えた臨時便が出る (Priority: P1)

**Goal**: 同じキー（航路・港・出港日・船）に定期便と臨時便が来たら、一覧の並び順に関係なく臨時便を優先する。前の回の臨時便の行も、定期便の欠航で上書きしない。定期便の詳細ページが取れない回も、臨時便が寄る港に船名なしの行を出さない（FR-005〜FR-007・FR-015）。

**Independent Test**: 9/7 の一覧（上りの欄に定期便 `cancel alert`・臨時便 `temporary alert`）を2通りの並び順で読ませ、那覇・名瀬のクロスが `extra`、本部・与論・和泊・亀徳のクロスが `cancelled` であることを確かめる（SC-001）。

### 同じ回の優先（research R4）

- [ ] T010 [US1] `scraper/tests/test_marix_line.py` にテストを足す（実装の前に落ちることを確かめる）。今日 2026-09-07、`@pytest.mark.parametrize("extra_first", [True, False])` で一覧の並び順を入れ替える:
  - (a) `parse_departures()` の結果で、上り・クロス・9/7 の那覇（07:00）・名瀬（21:20）がそれぞれ1行で `extra`、`source_url = EXTRA_UP_0907`
  - (b) 同じく本部・与論・和泊・亀徳のクロスが1行ずつで `cancelled`、`source_url = UP_0907`
  - (c) 同じキーの行が2本無い（`(route_id, port_id, departure_date, ship_name)` が重複しない）。`departure_duplicate_key` の警告が出ない
  - (d) `_run_departures()` で DB に書いた後も (a)(b) のとおり（1キー1行）
- [ ] T011 [US1] 同じファイルにテストを足す：定期便が走るときは定期便を残す（FR-006）。`up_cancel_20260907.html` の港のクラスを全部 `normal` に、h1 の【欠航】を【通常運航】にした定期便と、9/7 の臨時便を読む → 那覇・クロスの行は定期便（`operating`、`source_url = UP_0907`）。`status_detail` の終わりに「（臨時便 07:00発あり）」、`extra_voyage_conflict` の警告が1件
- [ ] T012 [US1] `marix_line.py` に `_resolve_extra_conflicts(self, records: list[dict], extra_urls: set[str]) -> list[dict]` を作り、`parse_departures()` の最後（`parsed_departures` のログの前）で呼ぶ（research R4）:
  - 同じキーの行を、臨時便（`extra_voyage`）と定期便に分ける
  - 定期便の状態が `cancelled`・`suspended`・`skipped`・`unknown` → 臨時便の行を残す
  - それ以外 → 定期便の行を残し、`status_detail` の終わりに `（臨時便 HH:MM発あり）`（臨時便の出港時刻）を足して `extra_voyage_conflict`（キー・両方の URL）を出す
  - 臨時便同士・定期便同士の重複は触らない（Base が先の行を使う）
  - 返す行の順番は元の順を保つ
  - `make test-scraper`・`make lint-scraper`

### 前の回の行（research R5）

- [ ] T013 [US1] `scraper/tests/test_marix_line.py` にテストを足す（実装の前に落ちることを確かめる）:
  - (a) 9/7 の一覧（定期便＋臨時便）で `_run_departures()` → 臨時便を一覧から外した一覧で `_run_departures()` → 那覇・名瀬のクロスは `extra` のまま（US1-4）
  - (b) (a) の2回目を、臨時便を一覧に残したまま臨時便の詳細ページを 500 にして読む → 同じく `extra` のまま
  - (c) 9/7 の一覧で `_run_departures()` → 臨時便の詳細ページの那覇・名瀬の日付を「09月08日」に書き換えて `_run_departures()` → 9/7 の那覇・名瀬のクロスは `cancelled`（`source_url = UP_0907`）に戻り、9/8 に `extra` の行がある（research R7）
  - (d) DB の `extra` の行と同じキーの定期便が `operating` → 定期便で上書きする
- [ ] T014 [US1] `marix_line.py` に `_extra_rows_kept(self, route_ids: list[int], since: date) -> dict[tuple, str]` を作る（キー → `source_url`。`status = 'extra'` で `departure_date >= since` の行）。`_resolve_extra_conflicts()` で、臨時便の行が無いキーの定期便の行（状態が `cancelled`・`suspended`・`skipped`・`unknown`）について、DB の `extra` の行があり、その `source_url` が `extra_urls`（この回に詳細ページを読めた臨時便の URL）に無ければ、定期便の行を落とす（research R5）。`since` はこの回の定期便の行の出港日のいちばん前。`make test-scraper`・`make lint-scraper`

### 予備ルート（research R6）

- [ ] T015 [US1] `scraper/tests/test_marix_line.py` にテストを足す（実装の前に落ちることを確かめる）:
  - (a) SC-008：9/7 の一覧で定期便の詳細ページを 500 にして `parse_departures()` → 那覇・名瀬は臨時便の行だけ（船名なしの行が無い）。本部・与論・和泊・亀徳は船名なし（`ship_name = ""`）の `cancelled`
  - (b) 前の回に臨時便の行（那覇・名瀬・クロス・`extra`）を DB に書いた後、臨時便が一覧に無く定期便の詳細ページも 500 の回 → 那覇・名瀬の船名なしの行を作らない（DB の `extra` の行で見る）
  - (c) 定期便の詳細ページが 500 の回（臨時便なし）で `_run_departures()` → 那覇・名瀬・本部…に船名なしの `cancelled` の行ができる → 次の回に臨時便が出て、定期便の詳細ページは 500 のまま `_run_departures()` → 那覇・名瀬の船名なしの行が消え、クロスの `extra` の行がある。本部などの船名なしの行は残る
- [ ] T016 [US1] `marix_line.py` を直す（research R6）:
  - `parse_departures()` で、先に臨時便のブロックを処理して、臨時便の行の `(route_id, port_id, departure_date)` の集合を作る。`_fallback_departures()` に渡し、その集合にあるか、DB に同じ `(route_id, port_id, departure_date)` の `extra` の行（どの船でも。`_extra_rows_kept()` の結果を使う）があれば、その港の行を作らない。行の順番は一覧の順に戻す（T012 の「元の順を保つ」と合わせる）
  - `_upsert_departures(self, records)` を上書きする：`super()._upsert_departures(records)` の後、`extra_voyage` の行の `(route_id, port_id, departure_date)` について `ship_name = ""` の行を消す（`synchronize_session="fetch"`）。戻り値は Base のまま
  - `make test-scraper`・`make lint-scraper`

**Checkpoint**: T010・T011・T013・T015 が通る・既存テストが全部通る → コミット

---

## Phase 6: User Story 4 - 途中の港から出る臨時便が出る (Priority: P2)

**Goal**: 名瀬発などの臨時便の方向を、一覧の欄・行き先から決める（FR-009）。トップで、始発港を出る臨時便しか無い日のバッジを「臨時便」にする（FR-014）。

**Independent Test**: 9/27 の臨時便（名瀬港発 鹿児島新港向け）を上りの欄に置いて読ませ、上りの名瀬（9/27 05:50）が `extra` であることを確かめる（SC-003）。

### 方向（research R2）

- [ ] T017 [P] [US4] `scraper/tests/test_marix_line.py` にテストを足す（実装の前に落ちることを確かめる）:
  - (a) 上りの欄に `temporary alert`・`EXTRA_UP_0927`・info2「2026年9月27日 名瀬港発 2026年9月27日 鹿児島新港 向け」、今日 2026-09-27 → 上りの航路に名瀬・クロス・9/27 05:50 の `extra` の行。鹿児島の行は無い。`direction_unknown` が出ない
  - (b) 同じ便を、欄の無い一覧（`<html><body>` の直下に `div.status_single_cover`）に置く → 行き先「鹿児島新港 向け」で上り。結果は (a) と同じ
  - (c) 欄も無く、info2 が「2026年9月27日 名瀬港発」だけ → `direction_unknown` を出して読み飛ばす（今のまま）
  - (d) 既存の `HTML_NORMAL_DOWN_DELAYED_UP` などの結果が変わらない（既存テストがそのまま通ることで確かめる）
- [ ] T018 [US4] `marix_line.py` の `_parse_direction(self, info2_text: str, block: Tag | None = None) -> str | None` を直す（research R2）：今の始発港 → `block` の祖先の `div.down_stream_services`（下り）・`div.up_stream_services`（上り）→ 行き先（`那覇\S*\s*向け` → 下り、`鹿児島\S*\s*向け` → 上り）の順。`parse()`・`parse_departures()` から `block` を渡す。`make test-scraper`・`make lint-scraper`

### トップのバッジ（research R9、contracts/ui-status.md）

- [ ] T019 [P] [US4] `app/tests/Controller/StatusControllerTest.php` にテストを足す（実装の前に落ちることを確かめる）。既存の `testIndexCardMidwayExtraOnlyShowsExtraBadge()` と同じ道具（`createPortBoardData()`・`updateTestDeparture()`・`setRouteStatus()`・`findCard()`）を使う:
  - (a) `testIndexCardOriginExtraOnlyShowsExtraBadge`：航路が `NoService`、今日の便が始発港の Extra だけ（途中の港の行を消すか別の日にする）→ バッジが「◆ 臨時便」、`.route-extra` が「◆ 臨時便 〇〇 HH:MM発」、「便なし」が出ない（SC-007）
  - (b) `testIndexCardOriginExtraWithMidwayRegularKeepsRegularBadge`：始発港が Extra、途中の港に定期便の通常運航 → 今までどおり定期便のバッジ（通常運航）
  - (c) 航路が欠航で始発港が Extra → バッジは欠航のまま（既存の `testIndexCardShowsExtraDepartureUnderRouteBadge` と同じ結果を確かめる）
- [ ] T020 [US4] `app/src/Controller/StatusController.php` の `routesDepartingMidway()` で、`midwayDisplay()` が null のとき `$today->firstExtraDepartureOf($companyId, $direction)` が null でなければ `['kind' => 'badge', 'state' => null, 'status' => OperationStatusEnum::Extra]` にする。メソッドの docblock に「途中の港を出る便が無く、始発港を出る臨時便があれば「臨時便」（13-marix-extra-voyages FR-014）」を足す。`make test-php`・`make phpstan`・`make cs-php`

**Checkpoint**: T017・T019 が通る・既存テストが全部通る → コミット

---

## Phase 7: User Story 5 - トップのバッジは定期便で決まる (Priority: P2)

**Goal**: 航路単位（航路×日付）は定期便だけで決める。並び順で「不明」にならない（FR-008）。

**Independent Test**: 9/6・9/7 の一覧を2通りの並び順で `parse()` させ、航路単位が 9/6 下り `delayed`、9/7 上り `cancelled` であることを確かめる（SC-004）。

- [ ] T021 [P] [US5] `scraper/tests/test_marix_line.py` にテストを足す（実装の前に落ちることを確かめる）。`@pytest.mark.parametrize("extra_first", [True, False])`:
  - (a) 今日 2026-09-06、9/6 下りの欄に定期便（`route alert`）と臨時便（`temporary alert`）→ `parse()` の下り 9/6 が `delayed`。`unknown` の行が無い。`unknown_status_class` が出ない
  - (b) 今日 2026-09-07、9/7 上りの欄に定期便（`cancel alert`）と臨時便 → 上り 9/7 が `cancelled`
  - (c) 今日 2026-09-27、上りの欄に 9/27 の臨時便だけ → 上り 9/27 は `no_service`（`extra` の行を返さない）
  - (d) (a) で、一覧の臨時便のクラスを `route alert` にして（一覧に temporary が無い場合。research R1）、詳細ページで臨時便とわかる → 結果は (a) と同じ
  - (e) `parse()` の結果に `status = extra` の行が1つも無い（`operation_statuses` の ENUM に無いため）
- [ ] T022 [US5] `marix_line.py` の `parse()` で、`self._is_extra_voyage(block, detail_html)` が True のブロックは行を作らず、`seen` にも入れずに次へ（research R8）。`detail_html` は `getattr(self, "_detail_pages", {}).get(urljoin(SOURCE_URL, href))`（`fetch()` を通らずに `parse()` を呼ぶ既存テストのため `getattr`）。`make test-scraper`・`make lint-scraper`

**Checkpoint**: T021 が通る・既存テストが全部通る → コミット

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T023 [P] `scraper/scraper/scrapers/marix_line.py` 冒頭の docstring を書き足す：CSS class の対応に `temporary → extra`、臨時便の見分け方（R1）、方向の決め方（R2）、寄らない港は作らないこと（R3）、同じキーの優先（R4・R5）、予備ルートを臨時便に使わないこと・船名なしの行を消すこと（R6）、航路単位に書かないこと（R8）。確認日と例（2026-09-06 service6727・2026-09-07 service6731・2026-09-27 service6819）
- [ ] T024 [P] `specs/12-marue-extra-voyages/contracts/ui-status.md` の「出るところ」の `midwayDisplay()` の段落の後に「始発港を出る臨時便しか無い日は specs/13-marix-extra-voyages/contracts/ui-status.md」と1行足す
- [ ] T025 全部のチェックを流す：`make test-scraper`・`make lint-scraper`・`make test-php`・`make phpstan`・`make cs-php`・`make lint-php`・`make check-schema`・`make verify-prod`
- [ ] T026 `make up` → `make scraper-run` で、今の公式の一覧（臨時便なし）でエラー・新しい警告が出ないこと、`/ports`・トップが今と同じことを目で見る。`make notify-dry-run` で本文が崩れないこと。臨時便が出ていない日なので、臨時便の表示は T019 の画面と 12 の既存テストで代える
- [ ] T027 quickstart.md の本番の確認手順を、実装に合わせて直す（ログのイベント名 `extra_voyage_detail_missing`・`extra_voyage_conflict`、SQL）

**Checkpoint**: 全部通る → コミット → PR

---

## Dependencies & Execution Order

```
Phase 1 → Phase 2 → Phase 3 (US2) → Phase 4 (US3) → Phase 5 (US1)
                 ├→ Phase 6 (US4)  ※ T017〜T018 は Phase 3 の臨時便の行に依存。T019〜T020（PHP）は Phase 1 だけに依存
                 └→ Phase 7 (US5)  ※ Phase 2 の判定だけに依存
Phase 3〜7 → Phase 8
```

- Phase 2 の `_is_extra_voyage()` が全部のスクレイパーの Story の前提
- US1 は US2 の臨時便の行（T007）と US3 の寄らない港の扱い（T009）の上に乗る。T016 は T014 の `_extra_rows_kept()` を使う
- US5（`parse()`）と US2〜US1（`parse_departures()`）は別の関数で、並べられる
- PHP（T019〜T020）はスクレイパーと独立

## Parallel Examples

- Phase 1：T002（fixture）と T003（テスト用の関数）は別の作業
- Phase 6 と Phase 7：T019・T020（PHP）と T021・T022（`parse()`）は別のファイル・関数
- Phase 8：T023（docstring）と T024（12 の契約）

## Implementation Strategy

- **MVP**：Phase 1〜5（US2・US3・US1）。臨時便が寄る港に「臨時便」が出て、寄らない港に変な行が出ず、9/7 のような「欠航した便の代わりの臨時便」が並び順に関係なく出る。本番に出すのはここから
- **次**：Phase 7（US5）で、トップのバッジが並び順で「不明」になるのを直す。MVP と一緒に出すのが望ましい（9/6・9/7 のどちらも、臨時便が一覧で先だとトップが「不明」になるため）
- **最後**：Phase 6（US4）で名瀬発の臨時便とトップのバッジ。名瀬発は出る回数が少ない
- PR は1つ・デプロイは1回。スキーマの変更も新しい状態も無いので、スクレイパーと Web の順番は問わない（research R10）
