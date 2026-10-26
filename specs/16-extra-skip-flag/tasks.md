# Tasks: 臨時便の抜港をスクレイパーが行のフラグで持つ

**Input**: [plan.md](plan.md)・[spec.md](spec.md)・[research.md](research.md)・[data-model.md](data-model.md)・[contracts/ui-status.md](contracts/ui-status.md)
**Tests**: 書く（SC-001〜SC-004 をテストで確かめる）

各フェーズの終わりに `git commit` する（Constitution V）。

## Phase 1: Setup

なし（新しいライブラリ・設定は無い）

## Phase 2: Foundational（列とスクレイパーの土台。plan Phase A）

- [ ] T001 マイグレーション `skips_ports_after TINYINT(1) DEFAULT 0 NOT NULL` を app/migrations/Version20261027000000.php に足す（down は DROP）
- [ ] T002 [P] `skipsPortsAfter`（bool、既定 false）と getter/setter を app/src/Entity/DepartureStatus.php に足す
- [ ] T003 [P] `skips_ports_after = Column(Boolean, nullable=False, default=False)` を scraper/scraper/db/models.py の DepartureStatus に足す
- [ ] T004 scraper/scraper/scrapers/base.py：`_departure_hash()` は `skips_ports_after` が True のときだけ payload に足す。`_upsert_departures()` の INSERT・UPDATE で `skips_ports_after` を書く
- [ ] T005 scraper/tests/test_base_upsert.py：False の行のハッシュが列を足す前と同じ／True で書かれる／False → True で内容が更新される
- [ ] T006 `make migrate`・`make check-schema`・`make test-scraper` を通してコミット

## Phase 3: User Story 1 - 臨時便の抜港を取りこぼさずに知らせる（P1）🎯 MVP

**Goal**: 両スクレイパーが臨時便の行に `skips_ports_after` を書く（FR-001〜FR-005）
**Independent Test**: スクレイパーのテストで、10/27 下り・終点の1個前を抜く上り・9/6・9/7・9/27 の行のフラグが data-model.md の例どおり

- [ ] T007 [US1] scraper/scraper/scrapers/marue_ferry.py：臨時便の港ごとに「寄港順でその港より後・終点より前に、【臨時便】の並びに無い港があるか」を求め、`_extra_records()` の行に `skips_ports_after` を詰める（research R2）
- [ ] T008 [US1] scraper/tests/test_marue_ferry.py：10/27 波之上（鹿児島・名瀬 True、本部 False）／終点の1個前の名瀬を抜く上り（全行 True）／全港に寄る臨時便（False）／便検索とぶつかった港は抜港にしない／便検索の行は False
- [ ] T009 [US1] scraper/scraper/scrapers/marix_line.py：`_parse_detail_departures()` で臨時便の `no_status` の港を集め、寄る港の最後の位置までのあいだで行ごとに `skips_ports_after` を詰める。定期便・予備ルートの行は False（research R3）
- [ ] T010 [US1] scraper/tests/test_marix_line.py：9/6（鹿児島 True）／9/7（那覇 True・名瀬 False）／9/27（名瀬 False）／定期便の行は False
- [ ] T011 [US1] `make test-scraper`・`make lint-scraper` を通してコミット

## Phase 4: User Story 2 - 抜港の判断をスクレイパーの1か所にまとめる（P2）

**Goal**: Web はフラグを読むだけにし、逆算を消す（FR-006〜FR-008）
**Independent Test**: PHPUnit で、臨時便の行のフラグだけで「・抜港あり」が切り替わる

- [ ] T012 [US2] app/src/View/PortBoardEntry.php：`skipsPortsAfter` を足し、`noServiceShipNames`・`isCalling()` を消す
- [ ] T013 [US2] app/src/Service/PortBoardBuilder.php：`skipsPortsAfter` を詰め、`$hidden` と `noServiceShipNames` を消す
- [ ] T014 [US2] app/src/View/PortBoardDay.php：`firstExtraDepartureOf()` で、対象の臨時便のエントリーのどれかが `skipsPortsAfter` なら `skipsPorts = true`
- [ ] T015 [US2] app/src/View/PortBoard.php の `extraSkipsPortsOf()`・`isPortIn()`・`callsAt()`、app/src/View/PortBoardExtraDeparture.php の `withSkipsPorts()` を消す
- [ ] T016 [US2] app/src/Controller/StatusController.php：`routesWithExtra()` から `$portIds` と `extraSkipsPortsOf` の呼び出しを消す（使わなくなった `use` も）
- [ ] T017 [P] [US2] app/tests/View/PortBoardDayTest.php：フラグありで true／なしで false／状態が欠航の行は数えない／ほかの会社・方向は数えない
- [ ] T018 [P] [US2] app/tests/Service/PortBoardBuilderTest.php：`noServiceShipNames` のテストを `skipsPortsAfter` が渡るテストに置き換える
- [ ] T019 [P] [US2] app/tests/View/PortBoardTest.php・app/tests/View/PortBoardEntryTest.php：逆算・`isCalling()` のテストを消す
- [ ] T020 [US2] app/tests/Controller/StatusControllerTest.php：10/27 の「・抜港あり」のテストを名瀬の行にフラグを立てる形に直し、フラグなしでは出ないテストを足す
- [ ] T021 [US2] `make test-php`・`make phpstan`・`make cs-php`・`make lint-php` を通してコミット

## Phase 5: Polish

- [ ] T022 specs/15-extra-voyage-badge/contracts/ui-status.md・specs/15-extra-voyage-badge/research.md の R3 に「16-extra-skip-flag で変更」の注記とリンク（FR-011）
- [ ] T023 quickstart.md の確認（`make scraper-run` 後の SQL）を流し、すべてのチェックを通してコミット

## Dependencies

- Phase 2 → Phase 3・Phase 4（列が要る）
- Phase 3 と Phase 4 は独立（Web はフラグを読むだけ。テストはボードを手で組む）
- Phase 5 は最後

## Parallel

- T002・T003（別ファイル）
- T017・T018・T019（別のテストファイル）

## Implementation Strategy

MVP は Phase 2 + Phase 3（フラグが DB に入る）。Phase 4 で Web が読み始めた時点で、15 の逆算と置き換わる。Phase 3・4 は同じ PR で出す（片方だけだと、フラグが使われない、または逆算が消えて「抜港あり」が出なくなる）。
