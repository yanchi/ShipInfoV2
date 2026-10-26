# Tasks: 臨時便がある日の会社カードのバッジを「スケジュール変更」にする

**Input**: Design documents from `specs/15-extra-voyage-badge/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: 入れる。臨時便は台風のあとにしか出ず、本番で出るのを待って確かめられない。2026-10-27・09-07・09-27 の形をテストで再現する。テストは実装より先に書き、落ちることを確かめてから実装する。

**Story ラベル**: spec.md の User Story 番号（US1〜US3）。

**plan の Phase との対応**:

| plan | この tasks.md |
|---|---|
| A. バッジ | Phase 2（US1） |
| B. 抜港あり | Phase 3（US2） |
| C. 通知メールと文書 | Phase 4（US3）・Phase 5 |

**コミット**: 各 Phase の Checkpoint でコミットする（constitution V）。

**共通の注意**:
- 変えるのは Web だけ。スクレイパー・DB・マイグレーションは触らない
- 臨時便が無い日の表示・メールは変えない（FR-007・SC-003）。research R5 の表にあるテスト以外の期待値を変える必要が出たら、実装を止めて理由を確かめる
- 「臨時便がある」は `PortBoardDay::firstExtraDepartureOf()` が null でないこと（research R2）。新しい判定を作らない
- `StatusControllerTest` の港別テストのデータは `createPortBoardData()`（港別テスト運航会社の下り、港別テスト丸が今日の名瀬 05:50 を通常運航）と `addTodayDeparture($port, $ship, $status, 'HH:MM')` で作る。トップのボードの港の並びは `RouteStopRepository::findBoardStops()`（方向ごとにいちばん若い ID の有効な航路）。テストを書く前に、テスト DB での下りの並び（鹿児島・名瀬・亀徳・和泊・与論・本部）を確かめる
- Phase の終わりに `make test-php`・`make phpstan`・`make cs-php`・`make lint-php` が通ること

---

## Phase 1: Setup

- [X] T001 `make up` → `make test-php` が全部通ることを確認してから始める

**Checkpoint**: 既存テストが全部通る（コミットなし）

---

## Phase 2: User Story 1 - 臨時便がある日は「通常運航」と出さない (Priority: P1) 🎯 MVP

**Goal**: 今日その方向に臨時便があり、ふだんのバッジが通常運航・運航予定になる航路は「▲ スケジュール変更」（FR-001〜FR-003・FR-005）

**Independent Test**: 航路単位が通常運航、名瀬・本部に臨時便の行があるデータでトップを開き、下りのバッジが「▲ スケジュール変更」、下に「◆ 臨時便 名瀬 03:50発」が出る

### Tests for User Story 1

- [X] T002 [US1] `app/tests/Controller/StatusControllerTest.php` にテストを足す（実装の前に落ちることを確かめる）:
  - (a) SC-001：`createPortBoardData()`、`setRouteStatus(Operating)`、`addTodayDeparture('名瀬', '臨時丸', Extra, '03:50')`・`addTodayDeparture('本部', '臨時丸', Extra, '12:00')` → カードの `.status-badge` が「▲ スケジュール変更」で `href` が `/company/{id}`、注意書き（「公式サイトをご確認ください」）が無い、`.route-extra` に「◆ 臨時便 名瀬 03:50発」が入っている
  - (b) 臨時便が全部出港済みでも戻らない：(a) と同じで、名瀬・本部の臨時便を両方 `00:00` にする（今日の 0:00 は必ず実行時刻以前）→ 「▲ スケジュール変更」、`.route-extra` は「◆ 臨時便 名瀬 00:00発」（時刻が同じときは `firstExtraDepartureOf()` が寄港順で先の港を返す。今の `<` の比較のまま）
  - (c) US1-2：`setRouteStatus(NoService)`、港別テスト丸の今日の名瀬の行を運航予定（`updateTestDeparture(0, 'status', null)`）、`addTodayDeparture('本部', '臨時丸', Extra, '12:00')` → 「▲ スケジュール変更」
  - (d) 臨時便の行が抜粋で欠航なら数えない：`setRouteStatus(Operating)`、`addTodayDeparture('本部', '臨時丸', Cancelled, '12:00')` → 「✓ 通常運航」で、`.route-extra` が無い
  - (e) 条件付・遅延は変えない：`setRouteStatus(Delayed)`、本部に臨時便 → 「▲ 条件付・遅延」と注意書き
  - (f) 不明は変えない：`setRouteStatus(Unknown)`、本部に臨時便 → 「？ 不明」のまま、`.route-extra` は出る
- [X] T003 [US1] research R5 の2本を書き換える（`app/tests/Controller/StatusControllerTest.php`）:
  - `testIndexCardOriginExtraWithMidwayRegularKeepsRegularBadge` → 名前を `testIndexCardOriginExtraWithMidwayRegularShowsScheduleChange` にし、期待を「▲ スケジュール変更」に。説明に「15-extra-voyage-badge で、臨時便がある日は通常運航にしない決まりに変えた」
  - `testIndexCardMidwayRegularPlusExtraKeepsRegularBadge` → 名前を `testIndexCardMidwayRegularPlusExtraShowsScheduleChange` にし、期待を「▲ スケジュール変更」に。説明は同じく（PR #87 レビューの決まりを変えたこと）
  - 両方とも `.route-extra` の期待はそのまま

### Implementation for User Story 1

- [X] T004 [US1] `app/src/Controller/StatusController.php`:
  - `routesDepartingMidway()` を `routeBadges()` に、`index()` で渡す変数を `routeBadges` に名前を変える。docblock の冒頭に「航路のバッジを航路単位の状態から変えるもの」と書き、航路単位が便なしの日の決まり（今の文）と、臨時便がある日の決まり（下）を並べる
  - ループの中で、今日その方向に臨時便がある（`$today->firstExtraDepartureOf($companyId, $direction) !== null`）航路について、次のどちらかなら `$result[$routeId] = ['kind' => 'changed', 'state' => null, 'status' => null]`（data-model.md の表）:
    - `$result` に入れなかった（航路単位でバッジが決まる）で、航路単位の状態が `Operating`
    - `$result[$routeId]` が `badge` で、`status === Operating` または `state === Scheduled`
  - `midwayDisplay()` の「臨時便は会社カードの専用の1行で伝える。定期便の通常運航と混ざっても『スケジュール変更』にしない」のコメントを、「臨時便の行を除いて決める。臨時便がある日の通常運航・運航予定は routeBadges() でスケジュール変更にする」に直す
- [X] T005 [US1] `app/templates/status/index.html.twig`：`routesDepartingMidway` → `routeBadges`、`midway` → `routeBadge` に名前を変える（`routeBadge.kind == 'badge'` と読めるように）。`changed` の分岐のコメントを「途中の港の状態がバラけている日、または臨時便がある日（15-extra-voyage-badge）」に直す
- [X] T006 [US1] `make test-php` で T002・T003 が通り、ほかのテスト（欠航・臨時便しか無い日・臨時便なし）が変わらず通ることを確かめる

**Checkpoint**: `make test-php`・`make phpstan`・`make cs-php`・`make lint-php` が通る → コミット

---

## Phase 3: User Story 2 - 臨時便の1行で抜港に気づける (Priority: P2)

**Goal**: 今日を出る臨時便の運航のどれかに抜港があれば、臨時便の1行の後ろに「・抜港あり」（FR-004）

**Independent Test**: 名瀬・本部に同じ船の臨時便、亀徳・和泊・与論に行なしのデータでトップを開き、1行が「◆ 臨時便 名瀬 03:50発・抜港あり」

### Tests for User Story 2

- [X] T007 [P] [US2] `app/tests/View/PortBoardTest.php` に `extraSkipsPortsOf()` のテストを足す（実装の前に落ちることを確かめる）。下りの港を6つ（鹿児島・名瀬・亀徳・和泊・与論・本部。添字 0〜5。終点の那覇は行にしない）並べたボードを手で組む道具（例：`extraBoard(array $days)`。日ごとに `[港の添字 => list<PortBoardEntry>]`）を足す。エントリーは `companyId: 1`、`shipName`・`departureAt`・`arrivalAt` つき（同じ運航の臨時便は同じ `arrivalAt`）:
  - (a) US2-1：今日 名瀬 03:50・本部 12:00 が波之上の Extra、亀徳・和泊・与論は行なし（または別の船の通常運航だけ）→ true
  - (b) US2-3（上りのボード）：今日 那覇 07:00・名瀬 21:20 がクロスの Extra、本部・与論・和泊・亀徳はクロスの Cancelled → true
  - (c) US2-2：今日 名瀬 05:50 だけが Extra → false
  - (d) 全港に寄る：今日 名瀬・亀徳・和泊・与論・本部が同じ船の Extra → false
  - (e) 便検索とぶつかった港：名瀬・本部が Extra、亀徳・和泊・与論が同じ船の運航予定（Scheduled）または通常運航 → false
  - (f) 日をまたぐ：今日 22:00 名瀬が Extra、明日 06:00 亀徳が Extra、明日 和泊は行なし、明日 10:00 与論が Extra → true
  - (g) 明日だけの臨時便（今日に Extra なし、明日に抜港あり）→ false
  - (h) 運航が2つ：船 A は全港に寄る、船 B は抜港あり（どちらも今日）→ true
  - (i) 同じ船が今日2回出る（名瀬 03:50・本部 12:00 は到着 13:50、鹿児島 18:00・名瀬 23:00 は翌日着）：到着予定が違うので別の運航。2回目の運航の鹿児島〜名瀬のあいだは抜港にならない（1回目の亀徳・和泊・与論が行なしなら true、全部 Extra なら false）。1回目のあいだの港に2回目の運航の行があるケースは作らない（research R3 の割り切り）
  - (k) 日が離れた同じ船の臨時便（PR #94 レビュー）：今日 名瀬 05:50（到着は今日 17:00）、2日後 本部 10:00（到着は2日後 12:00）がどちらもクロスの Extra → 別の運航なので false
  - (l) 船名が null のエントリー：今日 名瀬 03:50・本部 12:00 が船名 null の Extra（到着予定は同じ）→ まとめないので false
  - (m) 到着予定が null のエントリー：今日 名瀬・本部が同じ船の Extra で `arrivalAt` が null → まとめないので false
  - (j) 別の会社（`companyId: 2`）の Extra は見ない → false
- [X] T008 [P] [US2] `app/tests/Controller/StatusControllerTest.php` にテストを足す:
  - `addTodayDeparture()` に省略できる到着予定の引数（`?string $arrival = null`、今日の `'HH:MM'`）を足し、`setScheduledArrivalAt()` に渡す
  - (a) SC-004：`addTodayDeparture('名瀬', '臨時丸', Extra, '03:50', '13:50')`・`addTodayDeparture('本部', '臨時丸', Extra, '12:00', '13:50')` → `.route-extra` が「◆ 臨時便 名瀬 03:50発・抜港あり」
  - (b) 名瀬だけの臨時便 → 「◆ 臨時便 名瀬 03:50発」（「抜港あり」なし）

### Implementation for User Story 2

- [X] T009 [P] [US2] `app/src/View/PortBoardEntry.php` に `isCalling(): bool` を足す（その港に寄る便か）。`state === Scheduled`、または `state === Status` で `status` が Extra・Operating・Delayed・Unknown なら true。`app/tests/View/PortBoardEntryTest.php` に、全部の `OperationStatusEnum` と運航予定・便なし・情報なしの表でテストを足す
- [X] T010 [US2] `app/src/View/PortBoard.php` に `extraSkipsPortsOf(int $companyId, RouteDirectionEnum $direction): bool` を足す（research R3・data-model.md）:
  - 全日付の、その方向の行を順に見て、その会社の Extra のエントリーを `[行の添字, エントリー]` で集める（出港時刻が無いものは除く）
  - 船名と到着予定（`arrivalAt` の `Y-m-d H:i`）でまとめて運航にする。船名が空・null、または `arrivalAt` が null のエントリーは1つで1回の運航にする
  - 今日（`days[0]->date`）を出るエントリーを含む運航だけを見る
  - 運航の最初と最後の添字のあいだの行ごとに、運航の出港日の範囲の日で、同じ会社・同じ船のエントリーが `isCalling()` なら寄港。どの日も無ければ抜港 → true
  - docblock に「臨時便は寄らない港の行を作らない（12 の FR-006・13 の FR-003）ので、同じ船の寄る行が無い港を抜港とみなす」と、同じ運航の臨時便の行は到着予定（終点への到着）が同じであること、前日に始発港を出た運航は今日の最初の港から見ることを書く
- [X] T011 [US2] `app/src/View/PortBoardExtraDeparture.php`（`final readonly class`）のコンストラクタに昇格引数 `public bool $skipsPorts = false` を足す（readonly のプロパティ宣言には既定値を書けないので、プロパティとしては足さない）。docblock に「・抜港あり」を出すかと書く
- [X] T012 [US2] `app/src/Controller/StatusController.php` の `routesWithExtra()` にボード全体（`$fullBoard`）を渡し、`new PortBoardExtraDeparture($extra->portName, $extra->departureAt, $board->extraSkipsPortsOf($companyId, $direction))` で詰める
- [X] T013 [US2] `app/templates/status/index.html.twig` の臨時便の1行に `{% if extra.skipsPorts %}・抜港あり{% endif %}`。テキストに余計な空白が入らないようにする（T008 は `trim()` の完全一致）

**Checkpoint**: `make test-php`・`make phpstan`・`make cs-php`・`make lint-php` が通る → コミット

---

## Phase 4: User Story 3 - 通知メールの状況も揃える (Priority: P3)

**Goal**: 航路×日付が通常運航で、通常以外の港の行に臨時便が1つでもあれば、状況の頭は「スケジュール変更」（FR-006）

**Independent Test**: `IrregularServiceCollectorTest` の「通常運航・全部 Extra」が「スケジュール変更（臨時便あり）」、「Extra と条件付が混ざる」が「スケジュール変更（途中の港に変更あり）」

- [ ] T014 [US3] `app/tests/Service/IrregularServiceCollectorTest.php` の `testStatusTextForExtraPorts`（落ちることを確かめる）:
  - 書き換え：「通常運航・全部 Extra」→ `'スケジュール変更（臨時便あり）'`、「Extra と条件付が混ざる」（通常運航＋Extra＋Delayed）→ `'スケジュール変更（途中の港に変更あり）'`（research R5）
  - 足す：「通常運航・Cancelled だけ」→ `'通常運航（途中の港に変更あり）'`
  - そのまま：「行なし・全部 Extra」「便なし・全部 Extra」（臨時便あり）、「欠航は今までどおり」、「行なし・Extra と欠航」（情報なし（途中の港に変更あり））
  - docblock を「臨時便だけの日は、定期便に変更があるとは書かない。航路が通常運航で臨時便がある日は『スケジュール変更』（15-extra-voyage-badge）」に直す
- [ ] T015 [US3] `app/src/View/IrregularService.php` の `statusText()`：`$operating` で港の行に Extra が1つでもあれば、頭を `OperationStatusEnum::Operating->label()` から `'スケジュール変更'` にする（全部 Extra →「スケジュール変更（臨時便あり）」、混ざる →「スケジュール変更（途中の港に変更あり）」。research R4 の表）。コメントに「トップのバッジと同じく、臨時便がある日を通常運航と書かない（15-extra-voyage-badge）」を足す
- [ ] T016 [US3] `grep -rn '通常運航（臨時便あり）' app/` で残りが無いことを確かめる（`IrregularStatusMailerTest` など）

**Checkpoint**: `make test-php`・`make phpstan`・`make cs-php`・`make lint-php` が通る → コミット

---

## Phase 5: Polish & 文書

- [ ] T017 [P] `specs/12-marue-extra-voyages/contracts/ui-status.md` の「出るところ」の「定期便の通常運航と臨時便が混ざっても『スケジュール変更』にしない」と、「トップの会社カード（FR-016）」の「航路のバッジ・注意書きは変えない」の後ろに、「→ 15-extra-voyage-badge で変更（[contracts/ui-status.md](../../15-extra-voyage-badge/contracts/ui-status.md)）」を足す
- [ ] T018 [P] `specs/12-marue-extra-voyages/contracts/notification-mail.md` の状況の行の「通常運航（臨時便あり）」の後ろに、「→ 15-extra-voyage-badge で『スケジュール変更（臨時便あり）』に変更。臨時便とそれ以外が混ざる日は『スケジュール変更（途中の港に変更あり）』（[contracts/notification-mail.md](../../15-extra-voyage-badge/contracts/notification-mail.md)）」を足す
- [ ] T019 [P] `specs/13-marix-extra-voyages/contracts/ui-status.md` の「航路単位が便なしでない日」の節に、「臨時便がある日の通常運航・運航予定は 15-extra-voyage-badge で『▲ スケジュール変更』に変更」を足す
- [ ] T020 quickstart.md の手順でローカルのトップを開き、バッジ・「・抜港あり」・臨時便の無い航路が変わらないことを見る。`make notify-dry-run` で状況の文言を見る
- [ ] T021 `make test-php`・`make phpstan`・`make cs-php`・`make lint-php` が全部通る。会社詳細・港別ページ・異常の要約・凡例のテスト（`StatusControllerTest` の `testPorts*`・`testCompany*`・`testIndexAlertSummary*`）の期待を変えていないこと（FR-009）

**Checkpoint**: コミット

---

## Dependencies & Execution Order

- Phase 1 → Phase 2（US1）→ Phase 3（US2）→ Phase 4（US3）→ Phase 5
- US2 は US1 と別の部品（`PortBoard`・`PortBoardExtraDeparture`）だが、`StatusController`・`index.html.twig` を US1 で名前を変えたあとに触るので US1 の後にする
- US3 は US1・US2 と独立（`IrregularService` だけ）。先にやってもよい
- Phase 5 の T017〜T019 は別のファイルなので並べてできる

## Parallel Example

```text
# US2 のテストは別ファイルなので並べて書ける
T007 app/tests/View/PortBoardTest.php
T008 app/tests/Controller/StatusControllerTest.php
```

## Implementation Strategy

- MVP は US1（Phase 2）。緑の「通常運航」が出なくなるだけで、読み違いはいちばん大きく減る
- US2・US3 は順に足す。各 Phase でコミットし、Phase ごとに出してもよい
