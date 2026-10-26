# Tasks: マルエーフェリーの臨時便を港別ステータスに出す

**Input**: Design documents from `specs/12-marue-extra-voyages/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: 入れる。臨時便の実例は 2026-10-26 の波之上の1件だけで、本番で臨時便が出るのを待って確かめることはできない。そのため保存版を使った自動テストで確かめる。テストは実装より先に書き、落ちることを確かめてから実装する。

**Story ラベル**: spec.md の User Story 番号（US1〜US5）。

**plan の Phase との対応**:

| plan | この tasks.md |
|---|---|
| A. 状態「臨時便」を足す | Phase 2（T003〜T008） |
| B. 臨時便を読む | Phase 2（T009〜T011） |
| C. 行を作る・判定に混ぜない | Phase 3（US1）・Phase 4（US2） |
| D. 消す | Phase 5（US3） |
| E. トップの会社カードと文書 | Phase 6（US5）・Phase 7（US4）・Phase 8 |

**コミット**: 各 Phase の Checkpoint でコミットする（constitution V）。

**共通の注意**:
- DB のスキーマは変えない。マイグレーションは作らない
- `BaseScraper.fetch()` / `parse()` / `parse_departures()` のシグネチャは変えない。`raw_html_hash` は変えない
- 便検索から作る行の結果は変えない（SC-004）。既存テストの期待値を変える必要が出たら、実装を止めて理由を確かめる
- 臨時便の行の目印は `source_url`（船の詳細ページの URL）。状態では見分けない（research R5）
- テストの時刻は `fixed_now()` で固定する。2026-10-26 は既存の `NOW_1026 = datetime(2026, 10, 26, 10, 50)`・`run_1026()`・`NAMINOUE_25492`（波之上の詳細ページの URL）を使う
- PHP の Enum（T003）より先に、スクレイパーが `extra` を書くコードを本番に出さない（research R10）。同じ PR で出す
- Phase の終わりに、触った側のチェックが通ること（スクレイパー：`make test-scraper`・`make lint-scraper`、PHP：`make test-php`・`make phpstan`・`make cs-php`・`make lint-php`）

---

## Phase 1: Setup

- [X] T001 `make up` → `make test-scraper`・`make test-php` が全部通ることを確認してから始める
- [X] T002 `scraper/tests/fixtures/marue/ship_detail_naminoue_20261026.html` と `specs/12-marue-extra-voyages/samples/naminoue_detail_2026-10-26.html` が同じ中身であることを `cmp` で確かめる（違えば止めて相談する。fixture は新しく作らない）

**Checkpoint**: 既存テストが全部通る（コミットなし）

---

## Phase 2: Foundational（状態「臨時便」と臨時便の読み取り）

**Purpose**: 全部の Story が使う状態 `extra` と、詳細ページから臨時便を読む関数を作る。この Phase では行はまだ作らない（既存の結果は変わらない）。

### 状態「臨時便」（Web が先。research R4・R9・R10、contracts/ui-status.md）

- [X] T003 [P] `app/tests/Enum/OperationStatusEnumTest.php` に、`Extra` の label が「臨時便」、`isIrregular()` が true、`irregularCases()` に入ることのテストを足す → `app/src/Enum/OperationStatusEnum.php` に `case Extra = 'extra';` を足し、`label()`・`isIrregular()` の match に入れる
- [X] T004 [P] `app/tests/View/PortBoardEntryTest.php` に、Extra の entry が `isAlert()` true、出港時刻を過ぎても `isDeparted()` false（ほかの異常と同じ）のテストを足す → `app/src/View/PortBoardEntry.php` の `isAlert()` の配列に `OperationStatusEnum::Extra` を足す（docblock の「欠航・条件付・遅延・運休」に「臨時便」も足す）
- [X] T005 `app/templates/status/_status_badge.html.twig` に `status.value == 'extra'` → `<span class="status-badge status-badge--extra">◆ {{ status.label() }}</span>` を足す（skipped の次）。`app/templates/status/_status_warning.html.twig` の条件に `extra` を足す（コメントも直す）。`app/templates/status/_status_legend.html.twig` の抜港と欠航のあいだに `{status: Extra, note: '便検索に無い臨時の便。時刻・寄港地は定期便と違う'}` を足す（コメントに 12-marue-extra-voyages の contracts を足す）
- [X] T006 `app/templates/_site_styles.html.twig` に `.status-badge--extra { background: #dbe9ff; color: #0b4a8b; }`、`.port-entry--extra { border-left-color: #0b4a8b; background: #eef4ff; }`、`.route-extra`（文字色 `#0b4a8b`、小さめ）を、skipped の並びの次に足す
- [X] T007 [P] `scraper/scraper/db/models.py` の `OperationStatusEnum` に `extra = "extra"` を足す。コメント「skipped は港の行（departure_statuses）だけで使う」に extra も足す
- [X] T008 `app/tests/Controller/StatusControllerTest.php` に、Extra の港の行があると `/ports` と会社詳細ページ（`/company/{id}`）に「◆ 臨時便」と注意書きが出て、凡例に「臨時便」が出るテストを足す。`make test-php`・`make phpstan`・`make cs-php`・`make lint-php`

### 臨時便を読む（research R1〜R3、data-model の ExtraStop・ExtraVoyage）

- [X] T009 `scraper/tests/test_marue_ferry.py` にテストを足す（実装の前に落ちることを確かめる）。`_parse_extra_voyages(detail_html, ship_name)` を直接呼ぶ。`fixed_now(NOW_1026)` の中で、ルート・港は既存の `marue_with_ports` を使う:
  - (a) `ship_detail_naminoue_20261026.html` → 2便
    - 下り：鹿児島 10/26 16:00 出港、名瀬 10/27 03:00 入港/03:50 出港、本部 10/27 11:30/12:00、那覇 10/27 13:50 入港
    - 上り：那覇 10/28 05:00、本部 07:00/07:20、与論 09:50/10:10、和泊 12:10/12:40、亀徳 14:30/15:00、名瀬 18:30/19:20、鹿児島 10/29 07:30 入港
    - 下りの `skip_note` が「※ 亀徳港(徳之島)、和泊港(沖永良部島)、与論港(与論島)には寄港いたしません。」。上りは None
    - 【欠航】の「9月27日(火)」は臨時便ではないので読まない（警告も出ない）
  - (b) 臨時便が無い詳細ページ（`ship_detail_normal.html`）→ 空のタプル
  - (c) `status-archive` が無い HTML・None → None
  - (d) 次の書き換えのどれでも、その臨時便だけを入れずに `extra_voyage_unreadable`（船名・見出し・行）を1件出す。戻り値は `ExtraParse(voyages=(読めたほうの便,), complete=False)`（例：上りだけ曜日違い → 下りの1便が入る。PR #87 レビュー）。曜日違い（「10月28日(木)那覇港」）、航路に無い港（「伊延港」）、順番違い（本部と与論を入れ替え）、途中の港で出港なし（「本部港　07:00(入港)」だけ）、終点の入港なし（鹿児島の行を消す）、時刻が前の港より前、知らない形の行
  - (e) 見出しの括弧が半角・全角どちらでも読める
  - (f) 【臨時便(下り)】が2つ（日付違い）→ 下りの便が2つ（Edge Cases）
  - (g) `fixed_now(datetime(2026, 12, 30, 10, 0))` で「1月2日(土)」の臨時便 → 2027-01-02。曜日の確かめも 2027 年で行う（FR-010）
- [X] T010 `scraper/scraper/scrapers/marue_ferry.py` に `ExtraStop`・`ExtraVoyage`（frozen dataclass。data-model のとおり）と `ExtraParse`（`voyages`・`complete`）と `_parse_extra_voyages(detail_html: str | None, ship_name: str) -> ExtraParse | None` を作る（data-model「船ごとの読み取り結果」）
  - `div.status-archive` の `p` を上から読み、【臨時便(上り/下り)】で始めて、次の【…】・《…》・終わりで閉じる（research R1）
  - 行の正規表現はモジュールの定数（`_EXTRA_HEADING`・`_EXTRA_STOP`）にする
  - 港は `self._get_resolver().resolve()`、航路は `_route_directions()`、順番は `self._get_stops()` の `stop_order` で確かめる（research R2・R3）
  - 月日から年を決める処理は `_parse_voyages()` から `_nearest_date(month, day, today) -> date | None` に切り出して、両方で使う（`_parse_voyages()` の結果は変えない）
- [X] T011 `fetch()` で、詳細ページを取ったあとに `self._extra_voyages: dict[str, ExtraParse | None]` を作る（船ごと。取れなかった船は None）。`make test-scraper`・`make lint-scraper`

**Checkpoint**: 既存テストが全部通る（結果は変わらない）＋ T003〜T009 が通る → コミット

---

## Phase 3: User Story 1 - 臨時便が港別ページに出る (Priority: P1) 🎯 MVP

**Goal**: 臨時便の出港時刻のある港ごとに、状態「臨時便」の行を作る（FR-001〜FR-004・FR-009・FR-010）。定期便の判定に混ぜない（FR-014）。便検索の行とぶつかったら便検索を優先する（FR-003）。

**Independent Test**: `run_1026()` で、波之上の臨時便の行が9行できる（SC-001）。10/25 鹿児島発の定期便の判定は、臨時便の行が無いときと同じ（SC-007 の後半）。

### Tests（先に書く）

- [X] T012 [US1] `scraper/tests/test_marue_ferry.py` にテストを足す。`run_1026(db_session, id, down_1025_rows())`（10/26・10/28 の那覇発の検索は空）→ `_upsert_departures()` まで流す:
  - (a) SC-001：波之上の `source_url == NAMINOUE_25492` の行が9行
    - 下り：鹿児島 10/26 16:00、名瀬 10/27 03:50、本部 10/27 12:00
    - 上り：那覇・本部・与論・和泊・亀徳・名瀬（10/28）
    - 全部 `status == extra`、`scheduled_arrival_at` は下り 10/27 13:50・上り 10/29 07:30
    - 終点（下りの那覇・上りの鹿児島）の行は無い
  - (b) 下りの3行の `status_detail` が寄港しない港の文。上りは None
  - (c) `MARUE_SEARCH_DAYS_AHEAD=1` にすると 10/28 の上りの行は作らない（FR-009）
  - (d) 抜粋の「■10月28日（水）那覇港発上り便…臨時便運航」を「…欠航」に書き換えた鹿児島航路ページ（`kagoshima=`）では、上りの6行が cancelled で、詳細は抜粋の文（FR-004）
- [X] T013 [US1] FR-003 のテストを足す：
  - (a) 10/28 那覇の検索結果に波之上の定期便（07:00）がある → 那覇 10/28 の臨時便の行は作らない。便検索の行の詳細の後ろに「（臨時便 05:00発あり）」が付き、`extra_voyage_key_conflict` が1件出る
  - (b) 同じ時刻（05:00）なら詳細は変えず、警告も出ない
  - (c) DB に 10/28 那覇の波之上の便検索の行（`SEARCH_URL`）があり、この回にそのキーを検索していない → 作らない
  - (d) 便検索の記録が時刻なしの抜港（skipped）→ 臨時便の行は作らず、抜港の行の詳細は変えず、警告も出ない
  - (e) 10/28 那覇の検索結果に波之上の定期便（07:00。上り・始発港の出港日 10/28）があり、抜粋に「■10月28日（水）那覇港発上り便…欠航」→ 那覇以外の上りの臨時便の行（本部〜名瀬）は extra のまま（抜粋の行は定期便のもの。FR-004）
  - (f) 抜粋に「■10月26日（月）名瀬港発下り便…欠航」（10/25 鹿児島発の定期便の行）を足した鹿児島航路ページ → 10/26 鹿児島発の臨時便の下りの3行は extra のまま（この行は from_midway で日付が 10/26 なので、`_voyage_line()` の1段目でも当たってしまう。臨時便には from_midway の行を使わない。PR #87 レビュー）。あわせて「■10月26日（月）鹿児島新港発下り便…欠航」に書き換えると3行が cancelled（始発港から書いた行は当たる）
- [X] T014 [US1] FR-014 のテストを足す：臨時便の行（a の9行）を DB に入れた状態で、もう一度 `run_1026()` する。そのとき次が、臨時便の行を入れる前と同じになる
  - `_current_voyage`
  - 10/25 鹿児島発の定期便の `_voyage_departed()`・`_recorded_voyage()`
  - `_recorded_search_keys()`（10/28 の上りの臨時便を cancelled にしておいても、10/28 のキーが入らない）
  - `_needs_far_search(key, now)` を直接呼ぶ：10/28 那覇のキーに、`checked_at` が今の臨時便の行だけがある → True（臨時便の行の確認時刻で間隔を数えない）。同じキーに `checked_at` が今の便検索の行もある → False。`run_1026()` の中で確かめない（そのキーは抜粋の便の行で毎回検索されるので、直す前でも通ってしまう。analyze T1）

### Implementation

- [X] T015 [US1] `scraper/scraper/scrapers/marue_ferry.py` にモジュールの条件 `_SEARCH_ROWS = or_(DepartureStatus.source_url.is_(None), DepartureStatus.source_url == SEARCH_URL)` を作る。`_recorded_voyages()`・`_recorded_voyage()`・`_recorded_search_keys()`・`_needs_far_search()` の WHERE に足す（research R5）
- [X] T016 [US1] `parse_departures()` の最後に `_extra_records(records, now)` を呼んで、臨時便の行を足す（data-model「行の作り方」、research R4・R7）
  - 状態：抜粋の便の行のうち、`from_midway` でなく、方向が同じで日付が始発港の出港日と同じ行（`_voyage_line()` は使わない。1段目でも `from_midway` の行が日付で当たるため。research R4）が cancelled・suspended・delayed ならそれ＋`_ship_detail_text()`、それ以外は `extra`＋`skip_note`。ただし同じ船・同じ航路で、始発港の出港日が同じ定期便がこの回の便検索の記録か DB の `_SEARCH_ROWS` の行にあれば（`_departure_date(route_id, arrival_at)` で求める）、抜粋の行は当てずに `extra`
  - `source_url` は詳細ページの URL、`freeze_after_departure=True`、`replace_scope` は付けない
  - ぶつかったとき、記録に出港時刻があって臨時便と違えば、便検索の記録の `status_detail` に足し（None なら「臨時便 HH:MM発あり」だけ）、`extra_voyage_key_conflict`（船・航路・港・日付・両方の時刻）を出す
- [X] T017 [US1] `make test-scraper`・`make lint-scraper`。既存テストの期待値は変えない

**Checkpoint**: T012〜T014 が通る。既存テストが全部通る → コミット

---

## Phase 4: User Story 2 - 寄港しない港に臨時便が出ない (Priority: P1)

**Goal**: 寄港しない港に臨時便の行を作らない（FR-006）。臨時便の告知を、定期便の港別情報に使わない（FR-015）。

**Independent Test**: `run_1026()` で、10/26〜10/27 の亀徳・和泊・与論の下りに波之上の臨時便の行が0行（SC-002）。定型の注意書きのある詳細ページでも、定期便の亀徳・和泊・与論が抜港にならない（SC-007 の前半）。

- [X] T018 [P] [US2] `scraper/tests/test_marue_ferry.py` にテストを足す：T012 の流れで、10/26〜10/27 の下りの亀徳・和泊・与論に `source_url == NAMINOUE_25492` の行が無い（SC-002）（T016 で通るはず。通らなければ T016 を直す）
- [X] T019 [P] [US2] `scraper/tests/test_port_notice.py` にテストを足す：(b) 【臨時便(上り)】のブロックの直後（次の【…】が無い位置）に `<p>台風の影響や…</p>` を置いた HTML で、`_detail_body()` が None を返さず本文を返す（マーカーを飛ばさない。PR #87 レビュー）。(a) `ship_detail_naminoue_20261026.html` の `status-archive` の最後に `<p>台風の影響や…</p>` を足した HTML で、`extract_notice_text()` の結果に、次が入らない。入るのは【欠航】までの本文だけ
  - 【臨時便(下り)】〜【臨時便(上り)】の行
  - 「寄港いたしません」
  - 乗船手続きの行
- [X] T020 [US2] `scraper/scraper/utils/port_notice.py` の `_detail_body()` で、【臨時便…】の `p` から次の【…】の `p`（臨時便以外）または定型の注意書きの手前までを飛ばす。`BOILERPLATE_MARKER` の確かめは飛ばしている間も続ける（research R8）。モジュールの docstring にも書く
- [X] T021 [US2] `scraper/tests/test_marue_ferry.py` にテストを足す：T019 の HTML を詳細ページにして `run_1026()` し、今の便が亀徳・和泊・与論を通る日の定期便の行（`down_1025_rows()` の 10/26）が skipped にならない（SC-007）。`make test-scraper`・`make lint-scraper`

**Checkpoint**: T018〜T021 が通る → コミット

---

## Phase 5: User Story 3 - 臨時便の告知が変わったら追いかける (Priority: P2)

**Goal**: 取りやめた臨時便の行を、始発港を出る前なら消す。出たあとは残す（FR-008）。便検索の整理では消さない（FR-013）。

**Independent Test**: 臨時便の行がある DB で、告知を消した詳細ページを読ませる。出港前なら全港消え、出港後なら全港残る。

### Tests（先に書く）

- [X] T022 [P] [US3] `scraper/tests/test_base_departures.py` にテストを足す：`replace_scope` の行と同じ航路・港・日付に、別の `source_url` で別の船の行がある → 消えない。同じ `source_url` の別の船の行は今までどおり消える
- [X] T023 [US3] `scraper/tests/test_marue_ferry.py` にテストを足す。T012 の9行を DB に入れた状態から:
  - (a) 10/27 10:00 に、【臨時便(上り)】を消した詳細ページで実行 → 上りの6行が消える。下りは、名瀬（10/27 03:50）が出港済みでも始発（10/26 16:00）が出港済みなので3行とも残る
  - (b) 10/28 08:00 に、【臨時便(上り)】を消した詳細ページで実行 → 上りの6行が全部残る（那覇を 05:00 に出港済み。US3-3）
  - (c) 詳細ページの取得が失敗（404）→ 何も消えない
  - (d) 上りの臨時便だけが読めない（曜日違い）→ 何も消えない、`extra_voyage_unreadable`。下りの3行は今までどおり書かれる（FR-007）
  - (e) 10/28 那覇の検索結果がほかの船だけ（または他社運航）→ 波之上の那覇 10/28 の臨時便の行が残る（US3-4）
  - (f) 本文の名瀬 10/28 の出港を 19:20 → 20:00 に書き換え → 行の `scheduled_departure_at` が 20:00。10/28 10:30 に本部（07:20）の時刻を書き換えても、本部の行は変わらない（出港済み。US3-5）
  - (g) 上りの臨時便から与論を消した本文（10/28 05:00 より前に実行）→ 与論の行だけ消える
  - (h) 抜粋の上りの行が「…欠航」になる → 上りの6行が cancelled（US3-2）
  - (i) 前日に始発港を出た臨時便（本文を書き換えて、下りを 10/26 23:00 鹿児島発・10/27 15:00 名瀬・10/27 22:00 本部・10/28 那覇着にする）の行を DB に入れ、10/27 10:00 に【臨時便(下り)】を消して実行 → 名瀬・本部の行が残る（始発港の行の出港日 10/26 は範囲の外でも、出港済みの判定に使う。analyze U1）
  - (j) DB に何も無い状態で、10/27 05:00 に初めて読む → 下りは名瀬（10/27 03:50）・鹿児島（10/26 16:00）の行は作らず、本部（10/27 12:00）だけ作る（Edge Cases「初めて読んだときに始発港をもう出港している」）
  - (k) (j) のあと 10/27 10:00 に【臨時便(下り)】を消して実行 → 本部の行が残る（便の中に始発港の行が無いので出港済みとみなす。analyze U4）

### Implementation

- [X] T024 [US3] `scraper/scraper/scrapers/base.py` の `_upsert_departures()` のルール5で、scope のキーに `source_url` を足し、DELETE の条件に `DepartureStatus.source_url == source_url` を足す（research R6）。docstring のルール5も直す
- [X] T025 [US3] `scraper/scraper/scrapers/marue_ferry.py` で `_upsert_departures(records)` を上書きする（data-model「消し方」）
  - 親を呼んだあとに、`_extra_voyages` が None でない船の臨時便の行を読む（マルエーの航路・`scheduled_arrival_at > now`。**出港日では絞らない**）
  - 便（route_id, scheduled_arrival_at）ごとにまとめ、始発港（`_get_stops()[route_id][0]`）の行がある便で、`scheduled_departure_at` の最小が今より後の便だけ、出港日が今日〜`MARUE_SEARCH_DAYS_AHEAD` 日先で今回書かなかったキーの行を消す
  - 対象の船は `_extra_voyages` が None でなく `complete` が True の船だけ
  - 消した行の数を `extra_voyage_rows_deleted`（船・件数）でログに出す
  - 行を作るとき（T016 の中）、同じ船・航路で `scheduled_arrival_at` が違い、差が24時間未満の臨時便の行が DB にあれば `extra_voyage_arrival_changed`（船・航路・前と今の到着時刻）を出す（research R6 の既知の取りこぼし）。T023 に (l) として、名瀬の入港・終点の鹿児島の入港を書き換えたときにこの警告が1件出るテストを足す
  - 戻り値（created, updated）は親のまま
- [X] T026 [US3] `make test-scraper`・`make lint-scraper`

**Checkpoint**: T022〜T023 が通る → コミット

---

## Phase 6: User Story 5 - トップの会社カードで今日の臨時便が分かる (Priority: P2)

**Goal**: トップの会社カードの航路の下に「◆ 臨時便 鹿児島 16:00発」（FR-016）。異常の要約に臨時便（FR-017）。

**Independent Test**: 今日の下りに Extra の港の行（鹿児島 16:00）があり、航路単位は欠航の状態でトップを開くと、下りの行に「✗ 欠航」と「◆ 臨時便 鹿児島 16:00発」が両方出る。

- [ ] T027 [P] [US5] `app/tests/View/PortBoardTest.php` にテストを足す：`firstExtraDepartureOf(companyId, direction)` が出港時刻のいちばん早い Extra の便（港名・時刻）を返す。Extra が無ければ null、ほかの会社・ほかの方向・Extra 以外は見ない、出港済みでも返す
- [ ] T028 [P] [US5] `app/src/View/PortBoardExtraDeparture.php` を作る（`final readonly`、`string $portName`・`\DateTimeInterface $departureAt`）。`app/src/View/PortBoardDay.php` に `firstExtraDepartureOf()` を作る（行の `port` から港名を取る）
- [ ] T029 [US5] `app/src/Controller/StatusController.php` の `index()` で、`$fullBoard->days[0]`（今日）から航路ごとに `firstExtraDepartureOf(companyId, route->getDirection())` を求めて `routesWithExtra`（`[routeId => PortBoardExtraDeparture]`）をテンプレートに渡す。`app/templates/status/index.html.twig` の航路の `<li>` の最後（注意書きの後）に `<a href="{{ path('app_status_company', {id: company.id}) }}" class="route-extra small text-decoration-none">◆ 臨時便 {{ extra.portName }} {{ extra.departureAt|date('H:i') }}発</a>` を出す（contracts/ui-status.md）。同じファイルの `midwayDisplay()` は、Extra の entry を除いて今までどおり決め、除いた後に何も残らなければ `['kind' => 'badge', 'state' => null, 'status' => OperationStatusEnum::Extra]` を返す（research R9）
- [ ] T030 [US5] `app/tests/Controller/StatusControllerTest.php` にテストを足す
  - (a) 航路単位が欠航・今日の下りに Extra の行（鹿児島 16:00）→ トップの下りに「欠航」と「◆ 臨時便 鹿児島 16:00発」が両方出る
  - (b) Extra の行が無い方向には出ない
  - (c) 航路単位が便なしで、途中の港の Extra だけ（名瀬 03:50・本部 12:00）→ 航路のバッジが「臨時便」、下に「◆ 臨時便 名瀬 03:50発」
  - (d) トップの「欠航・条件付などの便」に臨時便の行が入る（FR-017）
  - (e) 航路単位が便なしで、途中の港が「定期便の通常運航（名瀬）＋臨時便（本部）」→ 航路のバッジは「通常運航」のまま（「スケジュール変更」にならない）、下に「◆ 臨時便 本部 HH:MM発」。PR #87 レビュー
  - (f) 途中の港が「定期便の欠航＋臨時便」→ 航路のバッジは「欠航」（Extra を除いて今までどおり）
- [ ] T031 [US5] `make test-php`・`make phpstan`・`make cs-php`・`make lint-php`

**Checkpoint**: T027〜T030 が通る → コミット

---

## Phase 7: User Story 4 - 臨時便が通知メールに載る (Priority: P3)

**Goal**: 臨時便の行が通知メールに「臨時便」として載る（FR-011。行は T003 の Enum で自動で入る）。臨時便だけの日の「状況」を「臨時便あり」にする（contracts/notification-mail.md）。

- [ ] T032 [P] [US4] `app/tests/Service/IrregularServiceCollectorTest.php` にテストを足す：Extra の港の行だけがある日も1件になる（`ports` に入る）
- [ ] T033 [P] [US4] `app/tests/Service/IrregularStatusMailerTest.php` にテストを足す：Extra の港の行が「- 那覇 05:00発 フェリー波之上：臨時便」の形で本文に出る（contracts/notification-mail.md）
- [ ] T034 [US4] `app/tests/Repository/DepartureStatusRepositoryTest.php` に、`findIrregularBetween()` が `status = 'extra'` の行を返すテストを足す
- [ ] T034a [US4] `app/tests/Service/IrregularStatusMailerTest.php` に「状況」のテストを足す：航路×日付が便なし・行なしで港が全部 Extra →「臨時便あり」、航路が通常運航で港が全部 Extra →「通常運航（臨時便あり）」、Extra と条件付が混ざる →「〜（途中の港に変更あり）」、航路が欠航 →「欠航」。→ `app/src/View/IrregularService.php` の `statusText()` を直す（contracts/notification-mail.md）。`make test-php`・`make phpstan`

**Checkpoint**: T032〜T034a が通る → コミット

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T035 [P] `scraper/scraper/scrapers/marue_ferry.py` 冒頭の docstring を書き足す。処理の流れの3（船別詳細ページ）に臨時便の読み取りを、港別に臨時便の行の作り方・消し方・`source_url` の目印・定期便の判定から除くことを書く
- [ ] T036 [P] `specs/9-marue-port-skip/contracts/ui-status.md` の冒頭に「臨時便は specs/12-marue-extra-voyages/contracts/ui-status.md」と1行足す（凡例の一覧がどこにあるか追えるように）
- [ ] T037 全部のチェックを流す：`make test-scraper`・`make lint-scraper`・`make test-php`・`make phpstan`・`make cs-php`・`make lint-php`・`make check-schema`・`make verify-prod`
- [ ] T038 `make up` → `make scraper-run` → `/ports`・トップ・凡例を目で見る（臨時便が出ていない日は T030 のテストの画面で代える）。`make notify-dry-run` で本文が崩れないこと
- [ ] T039 quickstart.md の本番の確認手順を、実装に合わせて直す（ログのイベント名・SQL）。`deploy/README.md` のロールバックの手順に「12-marue-extra-voyages 以降のイメージから戻すときは、先に `DELETE FROM departure_statuses WHERE status = 'extra'`」を足す（research R10）

**Checkpoint**: 全部通る → コミット → PR

---

## Dependencies & Execution Order

```
Phase 1 → Phase 2 ─┬→ Phase 3 (US1) ─┬→ Phase 4 (US2)
                   │                  └→ Phase 5 (US3)
                   ├→ Phase 6 (US5)   ※ Phase 2 の Enum だけに依存。US1 と並べられる
                   └→ Phase 7 (US4)   ※ Phase 2 の Enum だけに依存
Phase 3〜7 → Phase 8
```

- Phase 2 の T003（PHP の Enum）が全部の前提（research R10）
- US2 の T018 は US1 の T016 の結果を見る。T019〜T020 は US1 と独立
- US3 は US1 の行の作り方（T016）の上に乗る
- US5・US4 は PHP だけで、スクレイパーの Phase 3〜5 と並べられる

## Parallel Examples

- Phase 2：T003・T004・T007 は別ファイルなので同時に進められる
- Phase 3 と Phase 6：スクレイパー（T012〜T017）と PHP（T027〜T031）は別のツリー
- Phase 4：T018（marue_ferry のテスト）と T019（port_notice のテスト）
- Phase 7：T032・T033

## Implementation Strategy

- **MVP**：Phase 1〜4（US1・US2）。臨時便が港別ページに「臨時便」で出て、寄港しない港には出ない。ただし US3 が無いと、取りやめた臨時便が残るので、本番に出すのは Phase 5 まで入れてから
- **次**：Phase 6（US5）でトップに出す。Phase 7（US4）は通知の行は確かめるだけで、「状況」の文言だけ直す
- PR は1つ・デプロイは1回（PHP の Enum とスクレイパーを一緒に出すため。research R10）。急ぐ場合は、Phase 5 まで終わった時点で Phase 8 の T037 を流して PR を出し、Phase 6〜7 は別の PR にしてよい（Phase 2 で PHP の Enum・バッジは入っているので、港別ページは表示できる）
