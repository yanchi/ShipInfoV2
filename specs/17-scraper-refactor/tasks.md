# Tasks: スクレイパーを振る舞いを変えずに整理する

**Input**: [plan.md](plan.md)・[spec.md](spec.md)・[research.md](research.md)・[data-model.md](data-model.md)・[contracts/scraper-interface.md](contracts/scraper-interface.md)・[quickstart.md](quickstart.md)
**Tests**: 新しいテストは書かない（FR-002：テストの数を変えない）。既存の 336 件と、DB の行の前後比較（research R4）で確かめる

各フェーズ（US2 はステップごと）の終わりに `git commit` する（Constitution V・spec FR-010）。

**どのタスクにも共通の決まり**
- メソッド・定数は**切り取って貼るだけ**。名前・引数・中身・メソッドの並び順を変えない（FR-008）。見つけたバグは直さずメモして、最後に Issue にする（T021）
- 「確認」は quickstart の 2：`make test-scraper`（336 passed）・`make lint-scraper`・`make check-schema`・比較（`tests=336 diffs=0`）・ログの出来事の diff（差分なし）。通らなければ、直すのではなく移し方を戻す
- `docker compose exec -T scraper ruff format scraper/ tests/` で整形してから確認する

## Phase 1: Setup（比較の土台。plan Phase A）

- [X] T001 quickstart の 1 で、specs/17-scraper-refactor/ の snapshot_plugin.py・compare_snapshots.py・log_events.py をコンテナの /tmp にコピーし、基点のコミットのコードを /tmp/base に展開して /tmp/before1.jsonl・/tmp/before2.jsonl（どちらも 336 行）と /tmp/events_before.txt（53 種類）を取る。日をまたいだら、その日の最初の比較の前にやり直す。コミットはしない

## Phase 2: Foundational

なし（US1 が US2 の土台を兼ねる）

## Phase 3: User Story 1 - 両社で同じ処理を1か所にする（P1）🎯 MVP

**Goal**: `_load_routes()`・`_load_stops()` を `BaseScraper` に1つだけ置く（FR-004・research R1）
**Independent Test**: `grep -rn "def _load_routes\|def _load_stops" scraper/scraper/scrapers` が base.py だけ。確認が通る

- [X] T002 [US1] scraper/scraper/scrapers/base.py：`_upsert_departures()` の後ろに、scraper/scraper/scrapers/marix_line.py の `_load_routes()`（808–822 行）と `_load_stops()`（751–767 行、docstring つき）を移す。`_load_routes()` の `"鹿児島"`・`"那覇"` は `self.ROUTE_ORIGINS` の下り・上りに置き換え、`BaseScraper` に `ROUTE_ORIGINS: tuple[str, str]` を型注釈だけで宣言する（値は入れない。docstring に「(下りの始発港, 上りの始発港)。`_load_routes()` を使う会社が決める」）。`Route`・`RouteStop` を `scraper.db.models` から import に足す（base.py が既に import していればそのまま。research R1）
- [X] T003 [US1] scraper/scraper/scrapers/marix_line.py：クラスに `ROUTE_ORIGINS = ("鹿児島", "那覇")` を足し、`_load_routes()`・`_load_stops()` を消し、使わなくなった import（`Route`・`RouteStop` など、`ruff check` が F401 で出すもの）を消す
- [X] T004 [US1] scraper/scraper/scrapers/marue_ferry.py：クラスに `ROUTE_ORIGINS = ("鹿児島", "那覇")` を足し、`_load_routes()`（1671–1686 行）・`_load_stops()`（1687–1703 行）を消し、使わなくなった import を消す。`_get_stops()`・`_load_port_codes()`・`_marix_company_id()` は残す
- [X] T005 [US1] 確認してコミット（`refactor(scraper): 航路と寄港順の読み込みを BaseScraper にまとめる`）

## Phase 4: User Story 2 - マルエーフェリーを役割ごとに分ける（P1）

**Goal**: `marue_ferry.py` をパッケージ `marue_ferry/` の 8 ファイルに分ける（FR-003・FR-005・research R2）
**Independent Test**: `wc -l scraper/scraper/scrapers/marue_ferry/*.py` がどれも 600 以下。`from scraper.scrapers.marue_ferry import KAGOSHIMA_URL, SEARCH_URL, ExtraStop, ExtraVoyage, MarueFerry` がそのまま通り、確認が通る

ファイルとメソッドの対応は research R2 の表。行番号は T004 のあとでずれているので、メソッド名で探す。

- [X] T006 [US2] `git mv scraper/scraper/scrapers/marue_ferry.py scraper/scraper/scrapers/marue_ferry/__init__.py`（中身は変えない）。確認してコミット（`refactor(scraper): marue_ferry をパッケージにする（移すだけ）`）
- [X] T007 [US2] scraper/scraper/scrapers/marue_ferry/common.py を作る：`SEARCH_URL`〜`_CONDITIONAL_WORDS`、dataclass（`SearchRow`・`VoyageStatus`・`ShipInfo`・`RecordedVoyage`・`ExtraStop`・`ExtraVoyage`・`ExtraParse`）、`_VOYAGE_LINE`〜`_WEEKDAYS`、`_nearest_date`・`_parse_search_datetime`・`_iso` を __init__.py から移し、__init__.py は `from scraper.scrapers.marue_ferry.common import ...` で使う。common.py は `date`・`datetime` を import するので、scraper/tests/test_marue_ferry.py の `fixed_now()` を、差し替えるモジュールをタプル1つ（`marue_ferry`・`marue_ferry.common`）に持ってループで `patch` する形にする（research R3）。確認してコミット
- [X] T008 [US2] scraper/scraper/scrapers/marue_ferry/state.py を作る：`class MarueState(BaseScraper)` に `__init__`、data-model.md の表のインスタンス変数の型注釈（値は入れない）、`_route_directions`・`_get_resolver`・`_get_stops`・`_load_port_codes`・`_marix_company_id` を移す。__init__.py の `MarueFerry` は `MarueState` を継承する。data-model.md の「作る場所・読む場所」を grep で確かめ、違えば表を直す。確認してコミット
- [X] T009 [US2] scraper/scraper/scrapers/marue_ferry/fetch.py を作る：`class FetchMixin(MarueState)` に `fetch`〜`_search`（`_voyage_search_keys`・`_recorded_search_keys`・`_needs_far_search`・`_origin_departed`・`_normalized_origin_searches`・`_format_search_date`）を移し、`MarueFerry` の基底に足す。`time`・`settings`・`date`・`datetime` を読むので、scraper/tests/test_marue_ferry.py を直す：`fixed_now()` のタプルに `marue_ferry.fetch` を足す。`no_sleep()` は `scraper.scrapers.marue_ferry.fetch.time.sleep`（research R3）。確認してコミット
- [X] T010 [US2] scraper/scraper/scrapers/marue_ferry/ships.py を作る：`class ShipsMixin(MarueState)` に `_require_ship_statuses`・`_ship_detail_text`・`_parse_ships`・`_classify`・`_parse_voyages`・`_is_from_midway`・`_parse_status_text` を移し、基底に足す。`date` を読むので scraper/tests/test_marue_ferry.py の `fixed_now()` のタプルに `marue_ferry.ships` を足す。確認してコミット
- [X] T011 [US2] scraper/scraper/scrapers/marue_ferry/voyages.py を作る：`class VoyagesMixin(MarueState)` に `_skipped_record`〜`_recorded_voyage`（`_skipped_on_any_current_voyage`・`_skipped_on_current_voyage`・`_recorded_voyages`・`_future_voyage_status`・`_current_voyage_status`・`_ship_notices`・`_for_current_voyage`・`_departure_date`・`_for_voyage`・`_voyage_line`・`_match_voyage`・`_voyage_departed`）を移し、基底に足す。`fixed_now()` のタプルに `marue_ferry.voyages` を足す。確認してコミット
- [X] T012 [US2] scraper/scraper/scrapers/marue_ferry/extra.py を作る：`class ExtraMixin(MarueState)` に `_extra_records`・`_extra_skips_after`・`_warn_extra_arrival_changed`・`_delete_withdrawn_extra_rows`・`_extra_status`・`_has_regular_voyage`・`_recorded_search_keys_of`・`_note_extra_conflict`・`_parse_extra_voyages`・`_build_extra_voyage` を移し、基底に足す（`_upsert_departures` は移さない）。`fixed_now()` のタプルに `marue_ferry.extra` を足し、`test_extra_voyage_rows_respect_search_days_ahead` の `monkeypatch.setattr` を `"scraper.scrapers.marue_ferry.extra.settings.marue_search_days_ahead"` にする。確認してコミット
- [X] T013 [US2] scraper/scraper/scrapers/marue_ferry/statuses.py を作る：`class StatusesMixin(MarueState)` に `parse`・`_route_status`・`_worst_ship_status`・`parse_departures`・`_upsert_departures` を移し、基底に足す。`fixed_now()` のタプルに `marue_ferry.statuses` を足し、時計を読まなくなった `marue_ferry`（__init__.py）をタプルから外す。確認してコミット
- [X] T014 [US2] scraper/scraper/scrapers/marue_ferry/__init__.py を仕上げる：クラス本体を空にして `class MarueFerry(StatusesMixin, ExtraMixin, VoyagesMixin, ShipsMixin, FetchMixin)` にし、contracts/scraper-interface.md の 2 の名前を `__all__` で再エクスポートする。使わなくなった import を消す
- [X] T015 [US2] モジュールの docstring を段落ごとに移す（research R2：「処理の流れ・検索結果・raw_html_hash・valid_date」→ fetch.py、「航路単位・港別」→ statuses.py、「港別情報」→ voyages.py、「臨時便」→ extra.py）。文は変えない。__init__.py には全体の流れ（fetch → parse → parse_departures）と、どのファイルに何があるかだけを書く。common.py・state.py には1行の docstring
- [X] T016 [US2] 確認。`wc -l scraper/scraper/scrapers/marue_ferry/*.py` がどれも 600 以下、`python -c "from scraper.scrapers import SCRAPER_REGISTRY; print(SCRAPER_REGISTRY)"` がコンテナで通ることを見てコミット（`refactor(scraper): marue_ferry の __init__ を仕上げ、説明を各ファイルに移す`）

## Phase 5: User Story 3 - 臨時便の扱いで両社に共通するところをまとめる（P2）

**Goal**: 両社で決まりが同じ部分だけまとめる。違う部分は理由を残す（FR-006・research R5）
**Independent Test**: research R5 の表が実装と合っている。まとめないなら、コードの差分が無い

- [X] T017 [US3] scraper/scraper/scrapers/marue_ferry/extra.py と scraper/scraper/scrapers/marix_line.py の臨時便の処理（`_resolve_extra_conflicts`・`_extra_rows_kept`・`_extra_first_departures`・`_upsert_departures`）を並べて読み、specs/17-scraper-refactor/research.md の R5 の表（目印・ぶつかったとき・文・ログ・消す範囲・前の回の行）が実装と合っているか見直す。違えば表を直す
- [X] T018 [US3] T017 で、会社ごとの分岐・設定を足さずに（3つ未満で）まとめられる処理が見つかったときだけ、それを scraper/scraper/scrapers/base.py か scraper/scraper/utils/ に移し、確認する。見つからなければ research R5 の Decision のまま（コードの変更なし）。どちらでも research.md を直したらコミット

## Phase 6: Polish

- [X] T019 quickstart の 3：`grep -rn "def _load_routes\|def _load_stops" scraper/scraper/scrapers` が base.py だけ、行数がどれも 600 以下（SC-003・SC-004）
- [X] T020 `make test-scraper`・`make lint-scraper`・`make check-schema`・`make verify-prod`（本番用イメージで import が通る）・比較（`diffs=0`）・ログの出来事の diff（差分なし）を通す
- [X] T021 整理中にメモしたバグがあれば GitHub の Issue にする（FR-008）。無ければなにもしない。仕上げの変更があればコミット
- [ ] T022 **マージ・デプロイのあと**：quickstart の「本番」の SQL で、最初の定期スクレイプが両社とも成功し、公式ページが変わっていない会社の `departure_statuses.scraped_at` が一斉に進んでいないことを見る（SC-005）。PR の段階では未完了のまま残す

## Dependencies

- T001 → すべて（比較の「前」はコードに触る前にしか取れない）
- US1（T002–T005）→ US2（T006–T016）：分ける前に重複を消しておく（plan Phase B → C）
- US2 の中は順番どおり（同じ __init__.py と test_marue_ferry.py を少しずつ切り出すので、並列にしない）
- US3（T017–T018）は US2 のあと（extra.py が出来てから読み比べる）
- Polish は最後。T022 だけはマージ・デプロイのあと

## Parallel

- 並列にできるタスクは無い（全部が base.py・marue_ferry/__init__.py・test_marue_ferry.py のどれかを順に直す）
- T017 の読み比べだけは、US2 と別の人なら T012 のあと並べてできる

## Implementation Strategy

- MVP は US1（T001–T005）。これだけで出しても振る舞いは変わらず、重複が1つ減る
- US2 はステップ（T006〜T013）ごとにコミットするので、どこで止めても 336 件と `diffs=0` が通る状態で残る（FR-010）。PR は US1〜Polish を1つにまとめて出す（途中のコミットは履歴を追うために残す）
- US3 はコードを変えない見込み（research R5）。変える判断になったら、その分だけ T018 で足す
