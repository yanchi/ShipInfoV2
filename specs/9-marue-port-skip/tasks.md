# Tasks: 抜港を「抜港」と表示する

**Input**: Design documents from `specs/9-marue-port-skip/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ui-status.md, contracts/notification-mail.md, quickstart.md

**Tests**: 入れる。plan.md の「変更対象」でテストファイルを明示していて、FR-010（保存版で再現）・SC-001〜005 は自動テストでしか確かめにくいため。テストは実装より先に書き、落ちることを確かめてから実装する。

**Story ラベル**: spec.md の User Story 番号（US1〜US4）。

**plan の Phase との対応**:

| plan | この tasks.md |
|---|---|
| A. 共通の値 | Phase 2（Foundational）＋ Phase 3（US1 の画面）＋ Phase 4（US2） |
| B. 港別情報の読み取り | Phase 6（US3） |
| C. マルエー | Phase 3 の T015〜T017（skip → skipped）＋ Phase 7（US4）＋ Phase 8（時刻の無い抜港） |
| D. マリックス | Phase 5（US1 のマリックス） |

**コミット**: 各 Phase の Checkpoint でコミットする（constitution V）。

**共通の注意**:
- DB のマイグレーションはしない。`departure_statuses.status` は VARCHAR(32)、`operation_statuses.status` は MySQL の ENUM（research R1）
- 航路単位（`operation_statuses`）には `skipped` を書かない（FR-011）。`parse()` の `_route_status()`（マルエー）・一覧のクラス判定（マリックス）が `skipped` を返さないことをテストで縛る
- `_SEVERITY`（marue_ferry.py）には `skipped` を入れない（data-model §1）
- 既存のステータスの文言・見た目は変えない（FR-012）
- 文言（`抜港`・`≫`・凡例の説明）と色は contracts/ui-status.md から写す。勝手に言い換えない
- `BaseScraper.fetch()` / `parse()` / `parse_departures()` のシグネチャは変えない
- Phase の終わりに、PHP を触ったら `make test-php`・`make phpstan`・`make cs-php`・`make lint-php`、スクレイパーを触ったら `make test-scraper`・`make lint-scraper` が通ること

---

## Phase 1: Setup

- [ ] T001 `9-marue-port-skip` ブランチで `make up` → `make test-php`・`make test-scraper` が全部通ることを確認してから始める
- [ ] T002 [P] `specs/9-marue-port-skip/samples/kagoshima_2026-10-06.html` を `scraper/tests/fixtures/marue/kagoshima_20261006.html` に、`specs/9-marue-port-skip/samples/naminoue_detail_2026-10-06.html` を `scraper/tests/fixtures/marue/ship_detail_naminoue_20261006.html` にコピーする（research R10。中身は変えない。`samples/` は証跡として残す）

**Checkpoint**: 既存テストが全部通る。fixture が2つ増えている → コミット

---

## Phase 2: Foundational（ブロッキング前提）

**Purpose**: PHP・Python の両方で `skipped` を扱えるようにする。スクレイパーが `skipped` を書いても、画面・通知が落ちない状態を先に作る（plan「A を先にやる」）

**⚠️ CRITICAL**: この Phase が終わるまで US の実装を始めないこと

- [ ] T003 [P] `app/tests/Enum/OperationStatusEnumTest.php` に `Skipped` のケースを足す：`label()` が `抜港`、`isIrregular()` が true、`irregularCases()` に入る。既存の6つの値の `label()`・`isIrregular()` が変わっていないこと（FR-012）
- [ ] T004 `app/src/Enum/OperationStatusEnum.php` に `case Skipped = 'skipped';` を足す（`Delayed` と `Cancelled` のあいだ。data-model §1 の並び）。`label()` に `self::Skipped => '抜港'`、`isIrregular()` の true 側に `self::Skipped` を足す（T003 の後。research R1・R9）
- [ ] T005 [P] `scraper/scraper/db/models.py` の `OperationStatusEnum` に `skipped = "skipped"` を足す（`delayed` の下）。クラスの docstring かコメントに「港の行（`departure_statuses`）だけで使う。`operation_statuses` の ENUM には無い」と書く（FR-011）
- [ ] T006 `make check-schema` が通ることを確かめる（`departure_statuses.status` は String(32) なのでスキーマは変わらない。T005 の後）

**Checkpoint**: `make test-php`・`make phpstan`・`make test-scraper`・`make check-schema` が通る → コミット

---

## Phase 3: User Story 1 - 抜港の港の行が「抜港」と出る（画面・マルエー）(Priority: P1) 🎯 MVP

**Goal**: 港の行の `skipped` が、トップ・会社詳細・港別ページで `≫ 抜港`（オレンジ）と出て、異常の要約に入り、出港済みにならない。マルエーの告知で抜港と読み取った港が `skipped` で書かれる

**Independent Test**: `make test-php` で PortBoardEntryTest・PortAlertSummaryBuilderTest・StatusControllerTest が通る。`make test-scraper` で保存版（2026-10-06）から和泊発・与論発が `skipped`、亀徳発が `delayed`、`cancelled` が0件になる。quickstart.md「画面で見る」の手順で `≫ 抜港` が見える

### Tests for User Story 1（画面）

- [ ] T007 [P] [US1] `app/tests/View/PortBoardEntryTest.php` に、`status = Skipped`（state = Status）の行で `isAlert()` が true、予定出港時刻を過ぎた `$now` でも `isDeparted()` が false になるケースを足す（FR-002・FR-009）
- [ ] T008 [P] [US1] `app/tests/Service/PortAlertSummaryBuilderTest.php` に、`skipped` の港の行が異常の要約（トップの「欠航・条件付などの便」）に入るケースを足す（US1 シナリオ4）
- [ ] T009 [P] [US1] `app/tests/Controller/StatusControllerTest.php` に、`skipped` の港の行があるとき、港別ページ（`/ports`）・トップ（`/`）に `≫ 抜港` が出て行に `port-entry--skipped` が付くこと、注意書き「出港時間・寄港地が変更になってる可能性があるので公式サイトをご確認ください」が出ること、「ステータスの見かた」に `≫ 抜港` と「船は運航するが、この港には寄らない」があること、会社カード（航路単位）には `抜港` が出ないことを確かめるケースを足す（contracts/ui-status.md。既存のテストデータの作り方に合わせる）

### Implementation for User Story 1（画面）

- [ ] T010 [US1] `app/src/View/PortBoardEntry.php` の `isAlert()` の配列に `OperationStatusEnum::Skipped` を足す。`isDeparted()` は変えない（`isAlert()` の行を除外しているので抜港も出港済みにならない。data-model §5）
- [ ] T011 [P] [US1] `app/templates/status/_status_badge.html.twig` に `delayed` と `cancelled` の分岐のあいだで `{%- elseif status.value == 'skipped' -%}<span class="status-badge status-badge--skipped">≫ {{ status.label() }}</span>` を足す（research R8）
- [ ] T012 [P] [US1] `app/templates/status/_status_legend.html.twig` の一覧で、Delayed と Cancelled のあいだに `{status: constant('App\\Enum\\OperationStatusEnum::Skipped'), note: '船は運航するが、この港には寄らない'}` を足す。冒頭コメントの「8種類」を「9種類」にし、参照先に `specs/9-marue-port-skip/contracts/ui-status.md` を足す
- [ ] T013 [P] [US1] `app/templates/status/_status_warning.html.twig` の条件に `status.value == 'skipped'` を足し、冒頭コメントの「cancelled・delayed のときだけ出す」を「cancelled・delayed・skipped」にする（contracts/ui-status.md「注意書き」）
- [ ] T014 [P] [US1] `app/templates/_site_styles.html.twig` に `.status-badge--skipped { background: #ffe0c2; color: #8a3b00; }`（`--delayed` の下）と `.port-entry--skipped { border-left-color: #8a3b00; background: #fff3e8; }`（`.port-entry--delayed` の下）を足す（research R8）
- [ ] T015 [P] [US1] `app/src/DataFixtures/AppFixtures.php` に、今日〜3日先のどれかの港の行を `OperationStatusEnum::Skipped`（詳細テキスト例：「10月6日(火)与論港 抜港」）で1件足す（画面確認用。既存のサンプル行の作り方に合わせる）

### Tests for User Story 1（マルエー）

- [ ] T016 [US1] `scraper/tests/test_marue_ferry.py` に、保存版 `kagoshima_20261006.html`・`ship_detail_naminoue_20261006.html` を読ませるテストを足す（既存の `kagoshima.html`・`ship_detail_naminoue.html` のテストと同じ組み立て方。便検索は既存の `search_*.html` を流用するかテストの中で 10/5 下り・フェリー波之上の行を作る）
  - 10/6 の和泊発・与論発 → `skipped`、`status_detail` に抜港の告知の文（「10月6日(火)和泊港 抜港」など）が入る（FR-008）
  - 亀徳発 → `delayed`
  - その便の行に `cancelled` が0件（SC-001 の保存版の側）
  - `parse()` の航路単位の結果に `skipped` が無い（FR-011）
  - 既存の抜港のテスト（今 `cancelled` を期待しているもの）は `skipped` を期待するように直す

### Implementation for User Story 1（マルエー）

- [ ] T017 [US1] `scraper/scraper/scrapers/marue_ferry.py` の `_current_voyage_status()` で、`notice.kind == "skip"` のときを `OperationStatusEnum.cancelled` → `OperationStatusEnum.skipped` にする（data-model §4 の3。船が `cancelled` / `suspended` / `no_service` のときは今どおり船のステータスを先に返す。FR-005）。モジュール docstring の「抜港 → cancelled」を「抜港 → skipped」にする（T016 の後）

**Checkpoint**: PHPUnit で抜港のバッジ・異常の要約・出港済みにならない・凡例・注意書きが通る。pytest で保存版の和泊・与論が `skipped` になる。既存テストが全部通る → コミット

---

## Phase 4: User Story 2 - 通知メールでも「抜港」と出る (Priority: P1)

**Goal**: 抜港の港の行が通知メールの対象に入り、「抜港」と書かれる（テンプレート・送信ルールは変えない。research R9）

**Independent Test**: `make test-php` で T018〜T019 が通る。`skipped` の行がある状態で `make notify-dry-run` を動かし、その行が「…：抜港（…）」と出る

- [ ] T018 [P] [US2] `app/tests/Service/IrregularServiceCollectorTest.php` に、航路単位が `operating` で港の行だけ `skipped` の (航路, 日付) が通知の対象に入り、港の行の状態が `Skipped` になるケースを足す（US2 シナリオ1。`findIrregularBetween()` が `irregularCases()` から `skipped` を拾うことの確認）
- [ ] T019 [P] [US2] `app/tests/Service/IrregularStatusMailerTest.php` に、港の行が `skipped` のとき本文が `- 与論 フェリー波之上：抜港（10月6日(火)与論港 抜港）` の形になるケースを足す（contracts/notification-mail.md の例。「状況」の行には抜港が出ないこと）
- [ ] T020 [US2] T018・T019 が Phase 2 の enum の変更だけで通ることを確かめる。通らなければ `app/src/Service/IrregularServiceCollector.php`・`app/templates/email/` の通知テンプレートで `status.value` を直接見て分岐している所を探し、`label()`・`isIrregular()` を使うように直す（テンプレートの書き方は変えない）

**Checkpoint**: 通知のテストが通る。`make notify-dry-run` で抜港の行が「抜港」と出る → コミット

---

## Phase 5: User Story 1 - マリックスラインの「寄港しません」が「抜港」と出る (Priority: P1)

**Goal**: マリックスラインの便別詳細ページで `no_status`（「―」寄港しません）の港を `skipped` にする。便全体が欠航・運休ならそちら（research R7、FR-004・FR-005）

**Independent Test**: `make test-scraper` で `downstream_route_change.html` の寄港しない港が `skipped`、`downstream_cancel.html` の全港が `cancelled` のまま

### Tests

- [ ] T021 [US1] `scraper/tests/test_marix_line.py` を直す・足す
  - `downstream_route_change.html` の `no_status` の港の行 → `skipped`、`status_detail` に「寄港しません」が入る（今 `cancelled` を期待しているテストを直す。US1 シナリオ2、FR-008）
  - `downstream_cancel.html` の全港 → `cancelled` のまま、`skipped` が0件（SC-003）
  - 一覧の便のステータスが `cancelled`（または `suspended`）で、詳細ページの一部の港だけ `no_status` の HTML をテストの中で作り（`downstream_route_change.html` の便を欠航に書き換える）、その港が `skipped` にならず便のステータスになる（FR-005）
  - `parse()` の航路単位の結果に `skipped` が無い（FR-011）

### Implementation

- [ ] T022 [US1] `scraper/scraper/scrapers/marix_line.py` の `_departures_from_detail()` で、`_SKIPPED_PORT_CLASS`（`no_status`）の港を、`voyage_status` が `cancelled` / `suspended` ならそのステータス、それ以外は `OperationStatusEnum.skipped` にする。詳細テキストは今と同じく `div.exp`。モジュール docstring の「no_status → cancelled」を「no_status → skipped（便が欠航・運休ならそちら）」にする（T021 の後）

**Checkpoint**: pytest が全部通る。港別ページでマルエーとマリックスの抜港が同じ「抜港」で出る → コミット

---

## Phase 6: User Story 3 - 「寄港いたしません」と書かれても抜港と分かる (Priority: P2)

**Goal**: `port_notice.py` で「寄港いたしません」などを skip として読み、港名の後ろの括弧書きで列挙が切れる不具合を直す（research R2・R3、FR-006）

**Independent Test**: `make test-scraper` で test_port_notice.py の新しいケースと、保存版の「寄港いたしません」だけ版のマルエーのテストが通る。既存の誤検出0件のテストも通る（SC-005）

### Tests for User Story 3

- [ ] T023 [P] [US3] `scraper/tests/test_port_notice.py` に足す
  - skip になる：「与論港には寄港いたしません」「与論港には寄港致しません」「与論港には寄港しません」「与論港への寄港を取りやめ」「与論港への寄港を取り止め」「与論港の寄港は見合わせ」「与論港は寄港中止」（US3 シナリオ2、research R2）
  - 括弧書き：「※和泊港(沖永良部島)・与論港(与論島)には寄港いたしません。」で和泊・与論の2港とも skip、`sentence` は括弧を残した元の文（US3 シナリオ1、research R3）。全角の「和泊港（沖永良部島）」でも同じ
  - 括弧の中の読点：「スケジュール変更および条件付き運航(港変更や抜港、入出港時間などの変更を含む)といたします」で港別情報が0件（research R3 の「結果は同じ」）
  - 仮定の文を除く：「天候により与論港に寄港しない場合があります」「与論港に寄港しないことがあります」で0件（US3 シナリオ3）
  - 同じ港が抜港と条件付寄港の両方に出たら skip、告知の「抜港」の行と「寄港いたしません」の文が同じ港なら1件（spec Edge Cases）
  - 既存の定型の注意書き（「抜港(港に接岸できず…)や港変更になることがあります」など）で0件のテストが今のまま通る
- [ ] T024 [P] [US3] `scraper/tests/test_marue_ferry.py` に、`ship_detail_naminoue_20261006.html` から抜港の2行（「10月6日(火)和泊港 抜港」「10月6日(火)与論港 抜港」の `<p>`）をテストの中で取り除いた版（research R10。ファイルは増やさない）で、和泊発・与論発 → `skipped`、亀徳発 → `delayed`、`cancelled` 0件になるテストを足す（SC-001・FR-010 の「寄港いたしません」だけ版）

### Implementation for User Story 3

- [ ] T025 [US3] `scraper/scraper/utils/port_notice.py` を直す（T023 の後）
  - `_SKIP_PATTERN = re.compile(r"抜港|寄港(?:いたし|致し|し)ません|寄港(?:を|は)?(?:取りやめ|取り止め|とりやめ|見合わせ|中止)")` を足す（research R2）
  - `_keyword_pos(text, "skip")` を `_SKIP_PATTERN.search(text)` の開始位置にし、`_kinds()` の skip の判定も同じ正規表現にする
  - `_strip_parentheses(sentence)`：`\([^()]*\)` と `（[^（）]*）` を消す（入れ子は考えない）。`extract_port_notices()` で仮定の文の判定の後にかけ、`_sentence_notices()` には括弧を取った文で港・キーワードを探させ、`PortNotice.sentence` には元の文を入れる（plan「port_notice.py」）
  - モジュール docstring の「抜港 → skip」を、増やした表現と括弧書きの扱いに合わせて書き直す
- [ ] T026 [US3] T024 が通ることを確かめる。通らなければ `marue_ferry.py` の `_ship_notices()` の告知の組み立て（抜粋＋詳細本文）を見直す（T025 の後）

**Checkpoint**: pytest が全部通る（既存の誤検出0件のテストを含む）→ コミット

---

## Phase 7: User Story 4 - タグが複数あっても判定がぶれない (Priority: P2)

**Goal**: マルエーの船ブロックのタグを全部読み、並び順に関係なく船のステータス・条件付かどうか・スケジュール変更かどうかを決める。条件付＋スケジュール変更の船は、言及の無い港を通常運航にしない（research R4・R5、FR-007）

**Independent Test**: `make test-scraper` で、タグを入れ替えた船ブロックで全港の判定が同じになる（SC-004）。保存版で鹿児島・名瀬・本部が `delayed` になる

### Tests for User Story 4

- [ ] T027 [US4] `scraper/tests/test_marue_ferry.py` に足す
  - 保存版 `kagoshima_20261006.html` のフェリー波之上：`ShipInfo` が `status=delayed`・`conditional=True`・`schedule_changed=True`（US4 シナリオ1）
  - 同じ船ブロックのタグの順を入れ替えた HTML（テストの中で書き換える）で、`ShipInfo` と全港の判定が同じ（US4 シナリオ2、SC-004）
  - 「欠航」＋「条件付運航」のタグの船 → `status=cancelled`、その便の全港が `cancelled`、`skipped` 0件（US4 シナリオ3、SC-003）
  - 読めないタグが混ざっていても、読めたタグから決まり `unknown_status_text` の warning が出る
  - research R5 の表：条件付だけの船で言及の無い港 → `operating`（今のまま）、スケジュール変更だけ → `delayed`（今のまま）、条件付＋スケジュール変更 → 言及の無い港も `delayed`（保存版で鹿児島・名瀬・本部が `delayed`）

### Implementation for User Story 4

- [ ] T028 [US4] `scraper/scraper/scrapers/marue_ferry.py` を直す（T027 の後）
  - `ShipInfo` に `schedule_changed: bool = False` を足す（data-model §2）
  - `_parse_ships()`：`block.select_one("div.tag-list span")` を `block.select("div.tag-list span")` にして全部読む。`status` は読めたタグのうち `_SEVERITY` で一番重いもの（1つも読めなければ None）、`conditional` はどれか1つに「条件付」、`schedule_changed` はどれか1つに「遅延」か「スケジュール変更」。読めないタグは `unknown_status_text` の warning を出して無視する（research R4）
  - `_current_voyage_status()`：「条件付の船で告知がどれかの港にあれば、言及の無い港は `operating`」を `ship.conditional and not ship.schedule_changed` のときだけにする（data-model §4 の5）

**Checkpoint**: pytest が全部通る → コミット

---

## Phase 8: User Story 1 - 時刻・便が無い抜港の港でも「抜港」と出す (Priority: P1、Edge Case)

**Goal**: マルエーの便検索で抜港の港の日時が読めない・0件でも、今の便の抜港の港なら `skipped`（時刻なし）の行を作る。「便なし」や行の欠落にしない（research R6、spec Edge Cases）

**Independent Test**: `make test-scraper` で、日時「－」の検索結果と0件の検索結果のどちらでも、抜港の港の行が `skipped`・時刻なしになる。抜港でない港は今どおり

### Tests

- [ ] T029 [US1] `scraper/tests/test_marue_ferry.py` に足す（便検索の HTML は `search_ship.html`・`search_empty.html` をもとにテストの中で作る）
  - マルエーの行の出港日時が「－」：`_search()` が None でなく日時 None の行を返し、`search_datetime_missing` の warning が出る
  - 上の行で、今の便が同じ航路にありその港が抜港 → `skipped`・`departure_at`/`arrival_at` が None。抜港でない港 → その行は書かない（warning）
  - 0件の検索結果で、今の便が同じ航路にありその港が抜港で出港日が合う（下り：与論の `day_offset` 1、那覇 1 → 下船日と同じ日）→ 船名つき・時刻なしの `skipped`。出港日が合わない日・抜港でない港 → 今どおり `no_service`
  - 今の便が決まらない（船ブロックに無い）→ 今どおり（`skipped` を作らない）

### Implementation

- [ ] T030 [US1] `scraper/scraper/scrapers/marue_ferry.py` を直す（T029 の後。data-model §4「マルエーの便検索に日時・便が無い港」）
  - `_search()`：マルエーの行で日時が読めないとき、`return None` をやめて `departure_at=arrival_at=None` の `SearchRow` を残し、warning 名を `search_datetime_missing` にする。他社の行の扱いは変えない
  - `parse_departures()`：日時 None の行は、その船の今の便（`current_voyage`）が同じ航路にあり、その港が skip の告知なら `skipped`（時刻なし、詳細は告知の文）。それ以外は書かない
  - `parse_departures()`：0件のキーで、今の便が同じ航路にあり、その港が skip の告知で、出港日 ＝ 今の便の下船日 −（終点の `day_offset` − その港の `day_offset`）がキーの日付と合うなら `skipped`（船名つき・時刻なし）。それ以外は今の `no_service`
  - モジュール docstring に日時なし・0件の抜港の扱いを書き足す
- [ ] T031 [US1] `app/tests/View/PortBoardEntryTest.php`（または `app/tests/Service/PortBoardBuilderTest.php`）に、`skipped` で `departureAt` が null の行が「抜港」として出て `isDeparted()` が false になるケースを足す。落ちたら `app/src/View/PortBoardEntry.php`・`app/templates/status/_port_entry.html.twig` で時刻なしの行の扱いを直す

**Checkpoint**: pytest・PHPUnit が全部通る → コミット

---

## Phase 9: Polish & Cross-Cutting Concerns

- [ ] T032 [P] `specs/5-ui-readability/contracts/ui-status.md` の状態の表に、条件付・遅延と欠航のあいだで抜港の行（`≫`・抜港・オレンジの塗り・異常の要約に入る・出港済みにしない）を足し、`specs/9-marue-port-skip/contracts/ui-status.md` へのリンクを付ける
- [ ] T033 [P] `scraper/scraper/scrapers/marue_ferry.py`・`marix_line.py`・`scraper/scraper/utils/port_notice.py` の docstring・コメントに `cancelled` で抜港を表す古い記述が残っていないか `grep -n "抜港" scraper/scraper` で確かめて直す
- [ ] T034 全部のチェックを通す：`make test-php`・`make test-scraper`・`make phpstan`・`make cs-php`・`make lint-php`・`make lint-scraper`・`make check-schema`・`make verify-prod`
- [ ] T035 quickstart.md の「画面で見る」「通知メールで見る」の手順で確かめる（`make up` → `make migrate` → `departure_statuses` の1行を `skipped` に → `/`・`/ports`・`/company/{id}` と `make notify-dry-run`）
- [ ] T036 PR の説明に research R5（条件付＋スケジュール変更の船で言及の無い港を `delayed` にする理由）と、過去の `cancelled` の行はさかのぼって直さないこと（data-model §6）を書く

**Checkpoint**: 全チェックが通り、quickstart の確認が済んだ → コミット

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 依存なし
- **Foundational (Phase 2)**: Setup の後。全 US をブロックする
- **Phase 3 (US1 画面・マルエー)**: Phase 2 の後
- **Phase 4 (US2)**: Phase 2 の後（Phase 3 とは独立。enum だけに依存）
- **Phase 5 (US1 マリックス)**: Phase 2 の後（Phase 3 の画面があると見た目まで確かめられる）
- **Phase 6 (US3)**: Phase 3 の後（T024 は T017 の `skipped` に依存）
- **Phase 7 (US4)**: Phase 3 の後。Phase 6 とは別の関数だが同じ `marue_ferry.py`・`test_marue_ferry.py` を触るので、Phase 6 の後に順番にやる
- **Phase 8 (US1 時刻なし)**: Phase 6・7 の後（抜港の読み取りと今の便の判定が固まってから）
- **Polish (Phase 9)**: 全部の後

### User Story Dependencies

- **US1 (P1)**: Phase 2 の後。画面（Phase 3）が MVP の中心
- **US2 (P1)**: Phase 2 の後。US1 と独立して確かめられる
- **US3 (P2)**: US1 のマルエー（T017）の後
- **US4 (P2)**: US1 のマルエー（T017）の後。US3 と同じファイルなので順番に

### Within Each Phase

- テストを先に書いて落ちることを確かめる → 実装
- 同じファイルを触るタスク（`marue_ferry.py`・`test_marue_ferry.py`）は [P] にしない

---

## Parallel Examples

```bash
# Phase 2：PHP と Python の enum は別ファイル
Task: "T003 OperationStatusEnumTest に Skipped を足す"
Task: "T005 scraper/scraper/db/models.py に skipped を足す"

# Phase 3：テストを並べて書く
Task: "T007 PortBoardEntryTest"
Task: "T008 PortAlertSummaryBuilderTest"
Task: "T009 StatusControllerTest"

# Phase 3：テンプレート・CSS・fixture は別ファイル（T010 の後でなくてよい）
Task: "T011 _status_badge.html.twig"
Task: "T012 _status_legend.html.twig"
Task: "T013 _status_warning.html.twig"
Task: "T014 _site_styles.html.twig"
Task: "T015 AppFixtures.php"

# Phase 4 と Phase 5 は別の言語・別ファイルなので並べられる
Task: "T018・T019 通知のテスト"
Task: "T021・T022 マリックス"
```

---

## Implementation Strategy

### MVP First（US1 の画面＋マルエー）

1. Phase 1・2（enum）
2. Phase 3：保存版で和泊・与論が「抜港」になり、画面に `≫ 抜港` が出る
3. **STOP and VALIDATE**：quickstart「画面で見る」で確かめる。今回の報告（抜港なのに欠航）はここで直る

### Incremental Delivery

1. Phase 1〜3 → 今回の報告の修正（MVP）
2. Phase 4 → 通知メールも「抜港」
3. Phase 5 → マリックスも「抜港」（港別ページで2社がそろう）
4. Phase 6 → 「寄港いたしません」だけの告知でも拾う＋括弧書きの取りこぼしを直す
5. Phase 7 → タグの順でぶれない
6. Phase 8 → 時刻・便が無い抜港の港
7. Phase 9 → 仕上げ

1 PR にまとめる（plan に PR の分割は無い）。Phase ごとにコミットする。
