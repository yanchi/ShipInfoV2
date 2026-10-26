# Tasks: 先の便にも公式の便ごとの状態を出す

**Input**: Design documents from `specs/11-marue-voyage-lines/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: 入れる。SC-001〜006 は保存版を使った自動テストでしか確かめにくいため。テストは実装より先に書き、落ちることを確かめてから実装する。

**Story ラベル**: spec.md の User Story 番号（US1〜US3）。

**plan の Phase との対応**:

| plan | この tasks.md |
|---|---|
| A. 読み取り | Phase 2 の T003（`from_midway`）＋ Phase 4（US2） |
| B. 照合と判定 | Phase 2 の T004〜T005 ＋ Phase 3（US1 の先の便）＋ Phase 5（US3） |
| C. 検索の追加と文書 | Phase 3 の T009〜T010（FR-010）＋ Phase 6 |

**コミット**: 各 Phase の Checkpoint でコミットする（constitution V）。

**共通の注意**:
- 変えるのは `scraper/scraper/scrapers/marue_ferry.py` とそのテストだけ。DB・PHP・`utils/` は変えない
- `BaseScraper.fetch()` / `parse()` / `parse_departures()` のシグネチャは変えない。`raw_html_hash` に使う文字列は、航路ごとの「今日の始発港の便が出港済みか」を末尾に足す以外は変えない（出港時刻をまたぐと航路単位の判定が変わるため。PR #86 レビュー。デプロイ直後に1回だけ hash が変わる）
- 先の便には港別情報（`_ship_notices`・`_skipped_on_current_voyage`）を使わない（FR-004）
- 船のステータス（タグのうち一番重いもの、`_classify()`）の決め方は変えない（FR-006）
- テストの時刻は `fixed_now()` で固定する。2026-10-26 の保存版は `NOW_1026 = datetime(2026, 10, 26, 10, 50)` を基準にする
- Phase の終わりに `make test-scraper`・`make lint-scraper` が通ること
- **FR-011 の出港済みの今の便（Phase 5 の T014(g)〜(i)・T015・T016）は、テストを書きながら詰める**。`/speckit.analyze` を3回回して、そのたびにここから新しい穴が出た（analyze H2・H3・M2・M3）。机の上で詰めるより、テストで具体的な便を走らせたほうが早いと判断した。実装中に新しいケースや矛盾が見つかったら、テストを足し、data-model の「出港済み」「前回記録したその便のステータス」と research R7 を同じコミットで直す。spec の FR-011 と食い違う直しになるときは、実装を止めて相談する

---

## Phase 1: Setup

- [X] T001 `make up` → `make test-scraper` が全部通ることを確認してから始める
- [X] T002 [P] `specs/11-marue-voyage-lines/samples/` の3つを `scraper/tests/fixtures/marue/` にコピーする：`kagoshima_2026-10-26.html` → `kagoshima_20261026.html`、`naminoue_detail_2026-10-26.html` → `ship_detail_naminoue_20261026.html`、`akebono_detail_2026-10-26.html` → `ship_detail_akebono_20261026.html`（中身は変えない。`samples/` は証跡として残す）
- [X] T002a `scraper/tests/test_marue_ferry.py` に 2026-10-26 用のヘルパーを足す（`run_1020()` と同じ作り）：
  - 定数 `NOW_1026 = datetime(2026, 10, 26, 10, 50)`、`AKEBONO_17809 = "https://www.aline-ferry.com/status/route-kagoshima/ferry-akebono/17809/"`、`NAMINOUE_25492 = "https://www.aline-ferry.com/status/route-kagoshima/ferry-naminoue/25492/"`
  - `run_1026(db_session, company_id, searches, *, now=NOW_1026, kagoshima=None)`：`mock_search(searches)`、鹿児島航路ページ（既定は `kagoshima_20261026.html`）、上の2つの詳細ページ（それぞれの `ship_detail_*_20261026.html`）をモックして、`fixed_now(now)` の中で `fetch` → `parse` → `parse_departures` する。戻り値は `(scraper, records, departures, logs)`
  - 検索結果を作るヘルパー：`down_1025_rows()`（波之上、10/26 の名瀬 05:50・亀徳 09:40・和泊 12:00・与論 14:10・本部 17:10、下船 2026-10-26 19:00。本番の DB と同じ）、`up_1027_rows()`（波之上、10/27 の那覇 07:00・本部 09:20・与論 12:10・和泊 14:40・亀徳 17:00・名瀬 21:20、下船 2026-10-28 08:30）
  - 詳細ページの URL のモックが漏れていないこと（`ship_detail_fetch_failed` が出ない）をヘルパーの中で assert する

**Checkpoint**: 既存テストが全部通る。fixture が3つとヘルパーが増えている → コミット

---

## Phase 2: Foundational（便の行の照合をまとめる）

**Purpose**: US1・US3 が使う `_voyage_line()` を作る。この Phase では今の便・航路単位の結果を変えない（既存テストが全部そのまま通る）。

- [X] T003 `scraper/scraper/scrapers/marue_ferry.py` の `VoyageStatus` に `from_midway: bool` を足す。`_VOYAGE_LINE` で日付と方向の間の文字列を名前付きグループ（`place`）で取り、`_parse_voyages()` で、`place` の最後の「発」より前を `PortResolver.resolve()` で引き、その港が行の方向の航路の途中の港（`self._stops` の始発・終点以外）のときだけ True にする。港名は直書きしない。`_parse_ships()` は `fetch()` の中で便検索より前に呼ぶ（T010）ので、`fetch()` の最初で `self._stops` と `self._resolver = PortResolver.from_session(self.session)` を用意する（`parse_departures()` の中の resolver の作成はこれを使う形にする）。`_stops`・`_resolver` が無いとき（`_parse_ships()` を単独で呼ぶテスト）は、その場で読み込む。港名の無い行・始発港の行は False。「名瀬発那覇行き」は最後の「発」より前が「名瀬」なので True（research R7・data-model）
- [X] T004 `scraper/scraper/scrapers/marue_ferry.py` に `_voyage_line(ship, route_id, origin_date, arrival_date) -> VoyageStatus | None` を作る。1. 方向が同じで `departure_date == origin_date` の最初の行、2. 無ければ方向が同じで `from_midway` かつ `origin_date <= departure_date <= arrival_date` の最初の行、3. None（research R1・R7）。`_match_voyage()` の行探しをこれに置き換え、`_for_voyage()` に `arrival_date` を足す。呼び出し元（`_for_current_voyage()` は今の便の下船日、`_route_status()` は今日の始発港の検索結果の1行目の下船日）も直す。キャッシュのキーに `arrival_date` を足す。合わないときの挙動（船のタグ＋`voyage_not_in_excerpt`）はまだ変えない
- [X] T005 `scraper/tests/test_marue_ferry.py` にテストを足す：(a) `run_1026()`（または `kagoshima_20261026.html` を `_parse_ships()`）で、波之上の「鹿児島新港発」「那覇港発」の行が `from_midway=False`。「■10月22日（木）名瀬発下り便…」を差し込んだ行は True、「■10月27日（火）上り便…」（港名なし）は False、「■10月22日（木）名瀬発那覇行き下り便…」は True、(b) `_voyage_line()` が出港日の一致を範囲より優先する、(c) 始発港の行・港名の無い行は範囲では合わない、(d) 途中の港の行は範囲（出港日〜到着日）で合う

**Checkpoint**: 既存テストが全部通る（結果は変わらない）＋ T005 が通る → コミット

---

## Phase 3: User Story 1 - 公式が欠航と発表した先の便が「欠航」と出る (Priority: P1) 🎯 MVP

**Goal**: 抜粋に便の行がある先の便に、その状態を全港に出す（FR-001〜004）。2日先以降もすぐ反映する（FR-010）。

**Independent Test**: `run_1026()` に `down_1025_rows()` と `up_1027_rows()` を渡す。10/27 の那覇〜名瀬の6港が全部 `cancelled` になり、10/26 の和泊・与論・本部（今の便）は今までどおり `cancelled`。

### Tests（先に書いて落ちることを確かめる）

- [X] T006 [P] [US1] `scraper/tests/test_marue_ferry.py` に SC-001 のテスト `test_future_voyage_gets_voyage_line_status`：上の Independent Test（`run_1026()`）。10/27 の行の `status_detail` に「10月27日（火）那覇港発上り便…欠航」が入る
- [X] T007 [P] [US1] `scraper/tests/test_marue_ferry.py` にテストを足す：(a) `run_1026()` の鹿児島航路ページの 10/27 の行を「条件付運航」に差し替え → 全港 `delayed`。詳細ページ（`ship_detail_naminoue_20261026.html`）の「亀徳港…和泊港…与論港には寄港いたしません」が読まれていても `skipped`・`operating` にならない（FR-004）、(b) 抜粋に行の無い先の便は `status is None`・`status_detail is None`（SC-004。既存の `test_later_voyage_of_same_ship_is_scheduled` もそのまま通る）、(c) 便の行が1つだけで先の便に合う → 船のタグのステータス、(d) 先の便の行が「臨時便運航」：`up_1027_rows()` と同じ形で 10/28 那覇発上り（波之上、那覇 05:00・本部 07:20・与論 10:10・和泊 12:40・亀徳 15:00・名瀬 19:20、下船 2026-10-29 07:30。詳細ページの臨時便の時刻）の検索結果を作って渡す。本番では臨時便は便検索に出てこない（spec の範囲外）ので、テストのコメントに「仮のデータ」と書く → 10/28 の各港の行が `operating`・`status_detail is None`（US2 の後で通る。`xfail` にせず、US2 の Phase まで落ちたままでいい）

### Implementation

- [X] T008 [US1] `scraper/scraper/scrapers/marue_ferry.py` の `parse_departures()` で、今の便でないマルエーの行に `_future_voyage_status(row.ship_name, ships, route_id, row)` を使う。船ブロックが無い・便の行が0・`_voyage_line()` が None なら `(None, None)`。合えば、行が1つなら `ship.status`、2つ以上なら行の `status`。詳細は operating なら None、それ以外は `_ship_detail_text()` と同じ抜粋（research R3・data-model の表）。始発の出港日は `row.arrival_at.date() −（終点の day_offset − 始発港の day_offset）`

### FR-010（2日先以降の検索）

- [X] T009 [P] [US1] `scraper/tests/test_marue_ferry.py` にテストを足す（SC-005）：`run_1026()` で、2日先（10/28）と3日先（10/29）の全キーについて、DB に `checked_at = NOW_1026 − 1時間` の行を入れておく（既存の `test_far_searches_are_decided_per_key` の作り方）。抜粋の「10/28 那覇港発上り便」から決まる 10/28 の那覇発上りのキー（那覇・本部・与論・和泊・亀徳・名瀬）は検索され、10/28・10/29 の鹿児島発下りのキーは検索されない（`search_calls()` で確かめる）。抜粋の 10/28 の行は臨時便のもので、本番では便検索に出てこない。キーの決め方を確かめる仮のデータとして使うことを、テストのコメントに書く
- [X] T010 [US1] `scraper/scraper/scrapers/marue_ferry.py` の `fetch()` を「鹿児島航路ページ → `_parse_ships()` → 便検索 → 船別詳細ページ」の順に入れ替える。便の行から2日先以降の検索を足すキーの集合を作り（data-model「2日先以降の検索を足すキー」）、`offset >= 2 and not self._needs_far_search(key, now) and key not in forced` のときだけ飛ばす。戻り値の文字列（`raw_html_hash` の元）は変えない

**Checkpoint**: T006・T007(a)〜(c)・T009 が通る。T007(d) だけ落ちている。ほかの既存テストは全部通る → コミット

---

## Phase 4: User Story 2 - 「臨時便運航」で警告が出ず、便ごとの判定が効く (Priority: P2)

**Goal**: 「臨時便運航」を operating として読む（FR-005・FR-006）。

**Independent Test**: `kagoshima_20261026.html` を `_parse_ships()` に読ませて、警告0件・波之上の便の行3つ・船のステータスは `cancelled`。

- [X] T011 [P] [US2] `scraper/tests/test_marue_ferry.py` に SC-002 のテスト：上の Independent Test。行は `(10/27, 上り, cancelled)`・`(10/26, 下り, operating)`・`(10/28, 上り, operating)` の順。`unknown_status_text`・`unknown_voyage_status` のログが0件。あわせて `_parse_status_text()` のテスト：「臨時便運休」→ `suspended`、「臨時便条件付運航」→ `delayed`、「臨時便運航」→ `operating`（PR #85 レビュー）
- [X] T012 [US2] `scraper/scraper/scrapers/marue_ferry.py` の `_parse_status_text()` の**一番最後**（「通常」の判定の後、`return None` の前）に `"臨時" in text` → `OperationStatusEnum.operating` を足す。運休・条件付の語より先に当てない（research R4）

**Checkpoint**: T011・T007(d) が通る。既存テストが全部通る → コミット

---

## Phase 5: User Story 3 - ほかの便の告知で今の便を「欠航」と出さない (Priority: P2)

**Goal**: 便の行が読めて、出港前の今の便に合わなければ operating（FR-011。ただしタグのほうが行より重ければタグのまま）。出港済みの今の便は前回記録したステータスに港ごとに戻す。2日先以降の行が消えたらすぐ運航予定に戻す（FR-010 の後半）。

**Independent Test**: `run_1026(..., now=datetime(2026, 10, 28, 12, 0))` に、10/29 鹿児島発下り（波之上、乗船 18:00、下船 2026-10-30 19:00）だけの検索結果を渡す。10/29 便の行は `operating`。

> 4回目の `/speckit.analyze`（2026-10-26）の指摘 H4・M4・L3・L4・L5 は、spec・research・data-model・plan と下のタスク（T014(a)(m)・T016）に反映済み。

### Tests

- [X] T013 [P] [US3] `scraper/tests/test_marue_ferry.py` の `test_voyage_not_in_excerpt_keeps_ship_status` を `test_departed_voyage_not_in_excerpt_keeps_ship_status` に変える。今の便（あけぼの 10/20 那覇 07:00 発）は `NOW_1020`（11:39）で出港済みで、DB に記録も無いので、期待値は `cancelled` のまま（research R2）。`voyage_not_in_excerpt` の警告が1回で、`assumed="ship_status"` が付くことを足す
- [X] T014 [P] [US3] `scraper/tests/test_marue_ferry.py` にテストを足す：(a) SC-006（上の Independent Test）。10/30 の亀徳・和泊・与論も `operating`（詳細ページの臨時便の「寄港いたしません」が当たって抜港にならない。H4）、(b) 便の行が1つだけ（10/27 上り欠航）で 10/29 便 → `operating`、(c) `run_1026()` に `down_1025_rows()` を渡し、今の便（10/25 鹿児島発、出港済み、10/26 19:00 着）の 10/26 和泊・与論・本部の行は `cancelled` のまま（10/26 鹿児島新港発の臨時便の行に当たらない）、(d) 抜粋に便の行が0（`kagoshima_html(naminoue=("欠航", "台風のため欠航いたします。"))`。古い `kagoshima.html` が元なので `run_1026()` は使わず、既存の `mock_kagoshima()` と `TODAY_SEARCHES` で書く）→ 今の便は船のタグ（`cancelled`）、(e) 「■10月22日（木）名瀬発下り便…欠航」があり、今の便が 10/21 鹿児島発（出港前の時刻にする）→ `cancelled`、(f) 航路単位：今日の始発港の便が出港前で、行が読めて合わない → `operating`、(g) 出港後（research R7）：DB に 10/29 鹿児島発（波之上、下船 2026-10-30 19:00）の行を `status=operating` で入れておき、`run_1026(..., now=datetime(2026, 10, 29, 20, 0))` に 10/29 鹿児島 18:00 発と 10/30 の名瀬〜本部の検索結果（波之上、下船 2026-10-30 19:00）を渡す（鹿児島の行があるので出港済みになる）（鹿児島航路ページは 10/26 のまま。タグ「欠航」が残っている）→ 10/30 の行は `operating`。DB に行が無ければ `cancelled`（船のタグ）。さらに (h) M2：DB の 10/30 与論の行だけ `delayed`（詳細「与論港…港変更」）、ほかは `operating` で入れておく → 出港後も与論だけ `delayed`（詳細もそのまま）、ほかは `operating`。(i) M3：(g) と同じ DB で、10/29 鹿児島のキーの検索を失敗させる（`mock_search` の既定を None）→ DB の `scheduled_departure_at`（10/29 18:00）で出港済みと判定され、10/30 の行は `operating`（`assumed="recorded"`）、(j) PR #85 レビュー 🔴3：10/26 の fixture の波之上の 10/27 の行を「条件付運航」に差し替え（タグは「欠航」のまま。タグ ＞ 行）、今の便を 10/29 鹿児島発（出港前）→ `cancelled`（船のタグ）で、`voyage_tag_heavier_than_lines` の警告が出る。(k) タグが読めない船（`ship.status` が None）でも、`_skipped_on_current_voyage()` から呼ばれて例外にならず、行が合わなくても operating にならない（今の便は unknown のまま）。今までは作らなかった抜港の行もできない。(l) タグが「欠航」「条件付運航」、行はほかの便の欠航だけ、今の便は出港前 → 船のタグ（`cancelled`）で警告が出る。(m) 航路単位：今日の始発港の便が出港済みで、行が合わず、DB に記録がある → `operation_statuses` も記録のステータス（L5）

### Implementation

- [X] T015 [US3] `scraper/scraper/scrapers/marue_ferry.py` に出港済みの判定を作る（data-model「出港済み」）。今の便ごとに DB の `departure_statuses`（同じ船・同じ航路で下船日時の差が24時間未満）を1回だけ引いてキャッシュする `_recorded_voyage(ship_name, route_id, arrival_at)` を作る。持つのは `(port_id, departure_date) → (status, status_detail)` と `scheduled_departure_at` の一覧。出港済みは、この回の検索結果の同じ便の乗船日時と、DB の `scheduled_departure_at` の一番早いものが今以前か、始発の出港日が今日より前（data-model「出港済み」。M3）。`recorded_voyage_status`（NULL・skipped・unknown を除いて一番重いもの）もここで出す
- [X] T016 [US3] `scraper/scraper/scrapers/marue_ferry.py` の `_for_voyage()`（`_match_voyage()`）で、`ship.voyages` が1つ以上あって `_voyage_line()` が None のとき：出港前なら `replace(ship, status=operating, conditional=False, schedule_changed=False)` を返し、`voyage_not_in_excerpt` に `assumed="operating"` を付ける。出港済みなら、`ShipInfo` に足す `use_recorded: bool` を True にして返す（`status` は `recorded_voyage_status`、無ければ船のまま。`assumed="recorded"`／記録が無ければ `assumed="ship_status"` で `use_recorded` は False）。`_current_voyage_status()` では `use_recorded` のとき、その港・その日の前回の行があれば `(status, status_detail)` をそのまま返し、港別情報は重ねない。無ければ `ship.status` と抜粋（data-model「前回記録したその便のステータス」。M2）。operating にするときは `ShipInfo` に足す `assumed_operating: bool` を True にする。`assumed_operating` か `use_recorded` が True の今の便には、`_current_voyage_status()`（前回の行が無い港の道も含む）と `_skipped_on_current_voyage()` のどちらでも港別情報を当てない（H4・M4）。`len(ship.voyages) < 2` で早く返す今の分岐は、「0行なら船のまま」「1行で合えば船のまま」に分ける（data-model の表）。`_route_status()` は今日の始発港の1行目の乗船日時で出港済みを決め、出港済みなら `recorded_voyage_status`（無ければ船のタグ）を使う

- [X] T016a [US3] `scraper/scraper/scrapers/marue_ferry.py` の `_for_voyage()` の operating にする分岐に安全装置を足す：(1) `_SEVERITY.get(ship.status, 0) > max(_SEVERITY.get(v.status, 0) for v in ship.voyages)`、または (2) `ship.conditional` なのに `not any(v.conditional for v in ship.voyages)` なら船のまま返し、`voyage_tag_heavier_than_lines`（ship・タグ・行の一番重いもの・どちらの条件か）を警告する（research R2「安全装置」）。`_SEVERITY[...]` で引かない（タグが読めず `ship.status` が None の船が `_skipped_on_current_voyage()` から来て KeyError になる）。あわせて `_for_voyage()` の最初に `if ship.status is None: return ship` を入れる（タグが読めない船は便の行で判定を変えない。(1) が `0 > …` で False になり、operating に化けて抜港の行を作るのを防ぐ）。T014(j)(k)(l) で確かめる
- [X] T016b [US3] `scraper/scraper/scrapers/marue_ferry.py` の `fetch()` で、DB の `departure_statuses` で `ship_name != ""` かつ `status in (cancelled, suspended, delayed)` の行がある2日先以降のマルエーのキーも `forced` に足す。`operating`・`no_service`（`ship_name=""`）・`skipped`・NULL の行は含めない（research R5「行が消えたとき」・data-model）。テストを `scraper/tests/test_marue_ferry.py` に足す：DB に 10/28 那覇の行を `status=cancelled`・`checked_at = NOW_1026 − 1時間` で入れ、鹿児島航路ページの 10/28 の行を消す → 10/28 那覇のキーが検索され、行が `status is None` に戻る（SC-005 の後半）。あわせて、2日先の別のキーに `ship_name=""`・`status=no_service` の行と `skipped`・`operating` の行を入れておき、それらのキーは検索されない（間隔のとおり飛ばされる）ことを確かめる

**Checkpoint**: T013・T014・T016b のテストが通る。既存テストが全部通る → コミット

---

## Phase 6: Polish

- [X] T017 [P] `scraper/scraper/scrapers/marue_ferry.py` の先頭の docstring と `_for_voyage()`・`_match_voyage()` の docstring を、この機能の決まりに合わせて書き直す（便の行の照合、先の便、出港前の今の便、臨時便運航、2日先以降の検索）
- [X] T018 [P] `specs/4-departure-port-status/spec.md` の FR-021 の「それより後の便の行は「運航予定」とする」を、「ただし抜粋にその便の行があれば、その状態とする（11-marue-voyage-lines）」に書き換える（FR-008）
- [X] T019 `make format-scraper` → `make lint-scraper` → `make test-scraper` が全部通る
- [X] T020 quickstart.md の「ローカルで動かす」を実行して、`/ports` で先の便の状態が出ることを見る

**Checkpoint**: 全部通る → コミット

---

## Dependencies

```
Phase 1 → Phase 2 → Phase 3 (US1) → Phase 4 (US2) → Phase 5 (US3) → Phase 6
```

- US1・US3 は Phase 2 の `_voyage_line()` に依存する
- US2 は単独でもできるが、T007(d) の確認のため US1 の後にする
- US3 は US1 と同じ `_for_voyage()` を触るので、US1 の後にする（並べると衝突する）

## Parallel

- Phase 1：T002 は T001 と並べられる。T002a は T002 の後
- Phase 3：T006・T007・T009（テスト、同じファイルだが別の関数）は並べて書ける。実装の T008・T010 は順番に
- Phase 6：T017・T018 は並べられる

## Implementation Strategy

- **1回目のデプロイは Phase 1〜4（US1・US2）**。10/27 07:00 那覇発の便に間に合わせる（PR #85 レビュー）。Phase 4 の Checkpoint の後にこの PR に push して、マージ・デプロイする
- **2回目は Phase 5〜6（US3・安全装置・行が消えたときの検索）**。10/28 08:30（10/27 便が着いて、今の便が 10/29 便に移る時刻）までに出す
- デプロイのたびに、quickstart.md の「本番で確かめる」をやる。1回目の後は、15時の通知メールを一度見る（先の便が載るので、台風のときは件数が一気に増える）
