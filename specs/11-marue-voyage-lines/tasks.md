# Tasks: 先の便にも公式の便ごとの状態を出す

**Input**: Design documents from `specs/11-marue-voyage-lines/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: 入れる。SC-001〜006 は保存版を使った自動テストでしか確かめにくいため。テストは実装より先に書き、落ちることを確かめてから実装する。

**Story ラベル**: spec.md の User Story 番号（US1〜US3）。

**plan の Phase との対応**:

| plan | この tasks.md |
|---|---|
| A. 読み取り | Phase 2 の T003（`from_origin`）＋ Phase 4（US2） |
| B. 照合と判定 | Phase 2 の T004〜T005 ＋ Phase 3（US1 の先の便）＋ Phase 5（US3） |
| C. 検索の追加と文書 | Phase 3 の T009〜T010（FR-010）＋ Phase 6 |

**コミット**: 各 Phase の Checkpoint でコミットする（constitution V）。

**共通の注意**:
- 変えるのは `scraper/scraper/scrapers/marue_ferry.py` とそのテストだけ。DB・PHP・`utils/` は変えない
- `BaseScraper.fetch()` / `parse()` / `parse_departures()` のシグネチャは変えない。`raw_html_hash` に使う文字列も変えない
- 先の便には港別情報（`_ship_notices`・`_skipped_on_current_voyage`）を使わない（FR-004）
- 船のステータス（タグのうち一番重いもの、`_classify()`）の決め方は変えない（FR-006）
- テストの時刻は `fixed_now()` で固定する。2026-10-26 の保存版は `NOW_1026 = datetime(2026, 10, 26, 10, 50)` を基準にする
- Phase の終わりに `make test-scraper`・`make lint-scraper` が通ること

---

## Phase 1: Setup

- [ ] T001 `make up` → `make test-scraper` が全部通ることを確認してから始める
- [ ] T002 [P] `specs/11-marue-voyage-lines/samples/kagoshima_2026-10-26.html` を `scraper/tests/fixtures/marue/kagoshima_20261026.html` に、`specs/11-marue-voyage-lines/samples/naminoue_detail_2026-10-26.html` を `scraper/tests/fixtures/marue/ship_detail_naminoue_20261026.html` にコピーする（中身は変えない。`samples/` は証跡として残す）

**Checkpoint**: 既存テストが全部通る。fixture が2つ増えている → コミット

---

## Phase 2: Foundational（便の行の照合をまとめる）

**Purpose**: US1・US3 が使う `_voyage_line()` を作る。この Phase では今の便・航路単位の結果を変えない（既存テストが全部そのまま通る）。

- [ ] T003 `scraper/scraper/scrapers/marue_ferry.py` の `VoyageStatus` に `from_origin: bool` を足す。`_VOYAGE_LINE` で日付と方向の間の文字列を名前付きグループ（`place`）で取り、`_parse_voyages()` で「鹿児島」「那覇」を含めば True にする（research R7・data-model）
- [ ] T004 `scraper/scraper/scrapers/marue_ferry.py` に `_voyage_line(ship, route_id, origin_date, arrival_date) -> VoyageStatus | None` を作る。1. 方向が同じで `departure_date == origin_date` の最初の行、2. 無ければ方向が同じで `not from_origin` かつ `origin_date <= departure_date <= arrival_date` の最初の行、3. None（research R1・R7）。`_match_voyage()` の行探しをこれに置き換え、`_for_voyage()` に `arrival_date` を足す。呼び出し元（`_for_current_voyage()` は今の便の下船日、`_route_status()` は今日の始発港の検索結果の1行目の下船日）も直す。キャッシュのキーに `arrival_date` を足す。合わないときの挙動（船のタグ＋`voyage_not_in_excerpt`）はまだ変えない
- [ ] T005 `scraper/tests/test_marue_ferry.py` にテストを足す：(a) 2026-10-26 の fixture で、波之上の「鹿児島新港発」「那覇港発」の行が `from_origin=True`。「■10月22日（木）名瀬発下り便…」を差し込んだ行は False、(b) `_voyage_line()` が出港日の一致を範囲より優先する、(c) 始発港の行は範囲では合わない、(d) 途中の港の行は範囲（出港日〜到着日）で合う

**Checkpoint**: 既存テストが全部通る（結果は変わらない）＋ T005 が通る → コミット

---

## Phase 3: User Story 1 - 公式が欠航と発表した先の便が「欠航」と出る (Priority: P1) 🎯 MVP

**Goal**: 抜粋に便の行がある先の便に、その状態を全港に出す（FR-001〜004）。2日先以降もすぐ反映する（FR-010）。

**Independent Test**: 2026-10-26 の fixture と、10/27 那覇発上りの検索結果（`search_html()` で作る。波之上、乗船 07:00〜21:20、下船 2026-10-28 08:30）を読ませる。10/27 の那覇〜名瀬の6港が全部 `cancelled` になり、10/26 の和泊・与論・本部（今の便）は今までどおり `cancelled`。

### Tests（先に書いて落ちることを確かめる）

- [ ] T006 [P] [US1] `scraper/tests/test_marue_ferry.py` に SC-001 のテスト `test_future_voyage_gets_voyage_line_status`：上の Independent Test。10/27 の行の `status_detail` に「10月27日（火）那覇港発上り便…欠航」が入る
- [ ] T007 [P] [US1] `scraper/tests/test_marue_ferry.py` にテストを足す：(a) 先の便の行が「条件付」→ 全港 `delayed`。船の港別情報（抜粋・詳細ページの「寄港いたしません」）があっても `skipped`・`operating` にならない（FR-004）、(b) 抜粋に行の無い先の便は `status is None`・`status_detail is None`（SC-004。既存の `test_later_voyage_of_same_ship_is_scheduled` もそのまま通る）、(c) 便の行が1つだけで先の便に合う → 船のタグのステータス、(d) 先の便の行が「臨時便運航」→ `operating`・`status_detail is None`（US2 の後で通る。`xfail` にせず、US2 の Phase まで落ちたままでいい）

### Implementation

- [ ] T008 [US1] `scraper/scraper/scrapers/marue_ferry.py` の `parse_departures()` で、今の便でないマルエーの行に `_future_voyage_status(row.ship_name, ships, route_id, row)` を使う。船ブロックが無い・便の行が0・`_voyage_line()` が None なら `(None, None)`。合えば、行が1つなら `ship.status`、2つ以上なら行の `status`。詳細は operating なら None、それ以外は `_ship_detail_text()` と同じ抜粋（research R3・data-model の表）。始発の出港日は `row.arrival_at.date() −（終点の day_offset − 始発港の day_offset）`

### FR-010（2日先以降の検索）

- [ ] T009 [P] [US1] `scraper/tests/test_marue_ferry.py` にテストを足す（SC-005）：2日先のキーを前回の確認から1時間後に実行する（既存の `test_far_searches_are_decided_per_key` の作り方を使う）。抜粋にその日付の便の行があるキーは検索され、行の無いキーは今までどおり検索されない
- [ ] T010 [US1] `scraper/scraper/scrapers/marue_ferry.py` の `fetch()` を「鹿児島航路ページ → `_parse_ships()` → 便検索 → 船別詳細ページ」の順に入れ替える。便の行から2日先以降の検索を足すキーの集合を作り（data-model「2日先以降の検索を足すキー」）、`offset >= 2 and not self._needs_far_search(key, now) and key not in forced` のときだけ飛ばす。戻り値の文字列（`raw_html_hash` の元）は変えない

**Checkpoint**: T006・T007(a)〜(c)・T009 が通る。T007(d) だけ落ちている。ほかの既存テストは全部通る → コミット

---

## Phase 4: User Story 2 - 「臨時便運航」で警告が出ず、便ごとの判定が効く (Priority: P2)

**Goal**: 「臨時便運航」を operating として読む（FR-005・FR-006）。

**Independent Test**: 2026-10-26 の fixture を `_parse_ships()` に読ませて、警告0件・波之上の便の行3つ・船のステータスは `cancelled`。

- [ ] T011 [P] [US2] `scraper/tests/test_marue_ferry.py` に SC-002 のテスト：上の Independent Test。行は `(10/27, 上り, cancelled)`・`(10/26, 下り, operating)`・`(10/28, 上り, operating)` の順。`unknown_status_text`・`unknown_voyage_status` のログが0件
- [ ] T012 [US2] `scraper/scraper/scrapers/marue_ferry.py` の `_parse_status_text()` で、「欠航」の判定の後に `"臨時" in text` → `OperationStatusEnum.operating` を足す（research R4）

**Checkpoint**: T011・T007(d) が通る。既存テストが全部通る → コミット

---

## Phase 5: User Story 3 - ほかの便の告知で今の便を「欠航」と出さない (Priority: P2)

**Goal**: 便の行が読めて、出港前の今の便に合わなければ operating（FR-011）。出港済みの今の便は船のタグのまま。

**Independent Test**: 2026-10-26 の fixture で `fixed_now(datetime(2026, 10, 28, 12, 0))` にし、10/29 鹿児島発下り（波之上、乗船 18:00、下船 2026-10-30 19:00）だけを検索結果に出す。10/29 便の行は `operating`。

### Tests

- [ ] T013 [P] [US3] `scraper/tests/test_marue_ferry.py` の `test_voyage_not_in_excerpt_keeps_ship_status` を `test_voyage_not_in_excerpt_is_operating` に変え、期待値を `operating` にする（research R2）。`voyage_not_in_excerpt` の警告が1回で、`assumed="operating"` が付くことも確かめる
- [ ] T014 [P] [US3] `scraper/tests/test_marue_ferry.py` にテストを足す：(a) SC-006（上の Independent Test）、(b) 便の行が1つだけ（10/27 上り欠航）で 10/29 便 → `operating`、(c) 2026-10-26 10:50 の fixture で、今の便（10/25 鹿児島発、出港済み、10/26 19:00 着）の 10/26 和泊・与論・本部の行は `cancelled` のまま（10/26 鹿児島新港発の臨時便の行に当たらない）、(d) 抜粋に便の行が0（`kagoshima_html(nami=("欠航", "台風のため欠航"))`）→ 今の便は船のタグ、(e) 「■10月22日（木）名瀬発下り便…欠航」があり、今の便が 10/21 鹿児島発（出港前の時刻にする）→ `cancelled`、(f) 航路単位：今日の始発港の便が出港前で、行が読めて合わない → `operating`

### Implementation

- [ ] T015 [US3] `scraper/scraper/scrapers/marue_ferry.py` に出港済みの判定を作る（data-model「出港済み」）。`parse_departures()` で、今の便ごとに、この回の検索結果のうち同じ船・同じ航路・同じ下船日時の行の一番早い乗船日時を持っておく
- [ ] T016 [US3] `scraper/scraper/scrapers/marue_ferry.py` の `_for_voyage()`（`_match_voyage()`）で、`ship.voyages` が1つ以上あって `_voyage_line()` が None のとき：出港前なら `replace(ship, status=operating, conditional=False, schedule_changed=False)` を返し、`voyage_not_in_excerpt` に `assumed="operating"` を付ける。出港済みなら今までどおり船のまま（`assumed="ship_status"`）。`len(ship.voyages) < 2` で早く返す今の分岐は、「0行なら船のまま」「1行で合えば船のまま」に分ける（data-model の表）。`_route_status()` は今日の始発港の1行目の乗船日時で出港済みを決める

**Checkpoint**: T013・T014 が通る。既存テストが全部通る → コミット

---

## Phase 6: Polish

- [ ] T017 [P] `scraper/scraper/scrapers/marue_ferry.py` の先頭の docstring と `_for_voyage()`・`_match_voyage()` の docstring を、この機能の決まりに合わせて書き直す（便の行の照合、先の便、出港前の今の便、臨時便運航、2日先以降の検索）
- [ ] T018 [P] `specs/4-departure-port-status/spec.md` の FR-021 の「それより後の便の行は「運航予定」とする」を、「ただし抜粋にその便の行があれば、その状態とする（11-marue-voyage-lines）」に書き換える（FR-008）
- [ ] T019 `make format-scraper` → `make lint-scraper` → `make test-scraper` が全部通る
- [ ] T020 quickstart.md の「ローカルで動かす」を実行して、`/ports` で先の便の状態が出ることを見る

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

- Phase 1：T002 は T001 と並べられる
- Phase 3：T006・T007・T009（テスト、同じファイルだが別の関数）は並べて書ける。実装の T008・T010 は順番に
- Phase 6：T017・T018 は並べられる

## Implementation Strategy

- **MVP は Phase 1〜3（US1）**。10/27 の欠航が出るのはここまで。急ぐなら Phase 3 の後にいったんデプロイしてもいい
- 2026-10-26 のうちに Phase 5 まで入れてデプロイしたい。10/28 08:30 以降に 10/29 便が「欠航」と出る（US3）前に出す必要がある
