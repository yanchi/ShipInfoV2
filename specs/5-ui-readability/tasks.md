# Tasks: 運航情報画面の見やすさ改善

**Input**: Design documents from `specs/5-ui-readability/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/http-routes.md, contracts/ui-status.md, quickstart.md

**Tests**: 入れる。plan.md でテストファイルを明示していて、SC-009 で既存の表示内容が変わらないことを求めているため。

**Story ラベル**: spec.md の User Story 番号（US1〜US6）。US6 は PR1（ステータス表示・凡例）と PR3（共通ヘッダー・最終確認時刻）に分かれる。

**PR の分け方**（plan.md「実装の分割」）: 3つの PR に分け、順番にマージする。各 PR は `master` から切る。

| PR | ブランチ | Phase |
|---|---|---|
| PR1 | `5-ui-readability-ports` | Phase 1〜5（港別ページ・ステータス表示） |
| PR2 | `5-ui-readability-top` | Phase 6（トップ） |
| PR3 | `5-ui-readability-company` | Phase 7〜9（会社別・共通ヘッダー・最終確認時刻・仕上げ） |

**コミット**: 各 Phase の Checkpoint でコミットする（constitution V）。

**共通の注意**:
- `PortBoardBuilder` の判定ルールは変えない（SC-009）。`app/tests/Service/PortBoardBuilderTest.php` の既存のテストメソッドは変えずに通ること（テストメソッドの追加はよい）
- `StatusControllerTest` の港別の行の探し方（`li.port-row` の中の `.fw-bold` が「{港名}発」で始まる）は残す。テンプレートを変えるときは、この2つのクラスと文言を残す
- 表示用オブジェクトのメソッドは、現在時刻を引数（`$now`）で受け取る（単体テストで時刻を固定できるように）。Controller はその場で `new \DateTimeImmutable()` を作って渡す。機能テストでは「出港済み」の表示は確かめない
- テストは `make test-php` で全部通ること

---

# PR1: 港別ページとステータス表示（`5-ui-readability-ports`）

## Phase 1: Setup

- [X] T001 `master` から `5-ui-readability-ports` ブランチを切る。`make test-php` が全部通ることを確認してから始める
- [X] T002 `app/templates/base.html.twig` の `<head>` に `<style>` ブロックを追加して、このあとのタスクで使う共通の CSS クラスの置き場所を作る（アセットのビルド環境は入れない。plan.md の Structure Decision）。中身は T009・T028・T034・T035 で足す

**Checkpoint**: ブランチと CSS の置き場所ができている → コミット

---

## Phase 2: Foundational（ブロッキング前提）

**Purpose**: 3画面すべてで使う表示用オブジェクトの追加メソッドと、ステータス表示・便の行の部品

**⚠️ CRITICAL**: この Phase が終わるまで US の実装を始めないこと

- [X] T003 [P] `app/src/View/PortBoardEntry.php` に `public ?int $companyId = null` を追加する（コンストラクタの引数の最後に足す）。`app/src/Service/PortBoardBuilder.php` で、エントリーを作る2か所（ルール2：`$s->getRoute()->getFerryCompany()->getId()`、ルール3：`$operator->getId()`）で値を入れる。ルール4・5は入れない。判定のロジックには触らない（research R13）
- [X] T004 `app/src/View/PortBoardEntry.php` に次のメソッドを追加する（T003 と同じファイルなので T003 の後に行う）（data-model.md・research R7）
  - `isAlert(): bool` … `state === Status` かつ status が `Cancelled` / `Delayed` / `Suspended`
  - `isDeparted(\DateTimeInterface $now): bool` … `isAlert()` なら false。`departureAt` が null なら false。`departureAt < $now` かつ（`state === Scheduled` または status が `Operating`）なら true
  - `checkedAtDiffersFrom(?\DateTimeInterface $common): bool` … `checkedAt` が null なら false。`$common` が null なら true。それ以外は `Y-m-d H:i` で比べて違えば true
- [X] T005 [P] `app/src/View/PortBoardDirection.php` に `commonCheckedAt(): ?\DateTimeInterface` を追加する。`checkedAt` を持つエントリーの `Y-m-d H:i` が全部同じならその時刻（最初のもの）、1つも無いか違うものがあれば null（research R6）
- [X] T006 [P] `app/src/View/PortBoard.php` に `lastCheckedAt(): ?\DateTimeInterface`（ボード内の最大の `checkedAt`）を追加する
- [X] T007 [P] `app/tests/Service/PortBoardBuilderTest.php` とは別に `app/tests/View/PortBoardEntryTest.php` を作り、T004 の3メソッドをテストする
  - `isAlert`：Cancelled / Delayed / Suspended は true、Operating・NoService・Scheduled・NoInfo は false
  - `isDeparted`：Operating で出港時刻の1分後 → true、1分前 → false、Scheduled で過ぎた → true、Delayed・Cancelled・Suspended で過ぎた → false、`departureAt` が null → false
  - `checkedAtDiffersFrom`：同じ分で秒だけ違う → false、分が違う → true、`$common` が null → true、自分の `checkedAt` が null → false
- [X] T008 [P] `app/tests/View/PortBoardTest.php` を作り、T005 の `commonCheckedAt()`（全部同じ分 → その時刻、1つ違う → null、checkedAt が無い → null）と T006 の `lastCheckedAt()` をテストする。あわせて `app/tests/Service/PortBoardBuilderTest.php` に、ルール2・3のエントリーに `companyId` が入り、ルール4・5は null になるテストを**追加**する（既存のテストは変えない）
- [X] T009 `app/templates/status/_status_badge.html.twig` を `contracts/ui-status.md` の表のとおりに直す
  - 記号を変える：条件付・遅延「●」→「▲」、運休「-」→「■」、情報なし・不明は「？」（全角）
  - 便なしはバッジにせず、灰色の文字だけ（`<span class="status-none text-secondary">— 便なし</span>`）
  - 運航予定は白地に破線の枠（今の `style` 属性をやめて、T002 の `<style>` に `.badge-scheduled` を作る）
  - 情報なし・不明は薄い灰の塗り（`bg-secondary-subtle text-dark`）。運休は濃い灰（`bg-secondary`）
  - 既存の `bg-success`（通常運航）のクラスは残す（`StatusControllerTest` が見ている）
- [X] T010 `app/templates/status/_port_entry.html.twig` を新しく作り、`ports.html.twig` の便の1件分（今の `.port-entry` の中身）を移す。引数は `entry`・`day`（日付）・`now`・`commonCheckedAt`。この Phase では見た目は今のままでよい（T032 で2段にする）。`ports.html.twig` からはこのパーシャルを `include` する
- [X] T011 `app/templates/status/ports.html.twig` の各日付の `<section>` に `id="d-{{ day.date|date('Y-m-d') }}"`、各行の `<li class="list-group-item port-row">` に `id="r-{{ day.date|date('Y-m-d') }}-{{ direction.direction.value }}-{{ row.port.id }}"` を付ける（contracts/http-routes.md のアンカー）
- [X] T012 `make test-php` を実行する。T009 で文言（「● 条件付・遅延」など）を見ているテストがあれば、新しい記号に合わせて直す

**Checkpoint**: 表示用オブジェクトの追加メソッドとテストがある。ステータス表示が contracts/ui-status.md のとおり。既存テストが通る → コミット

---

## Phase 3: User Story 1 - 自分の港の便だけを見る (Priority: P1) 🎯 MVP

**Goal**: 港別ページを出発港・方向で絞り込める。フォームで保存した条件は次回も使われる。共有URLやリンクは保存を変えない

**Independent Test**: `/ports?port={和泊のID}&dir=down` で各日付に「和泊発→那覇」だけが出る。`save=1` で保存した後、`/ports` を開くと同じ絞り込みになる。`?port=all` では保存が残り、`?clear=1` で消える

### Tests for User Story 1

- [ ] T013 [P] [US1] `app/tests/View/PortFilterTest.php` を作り、`PortFilter` をテストする：`none()` は `isActive()` が false、港だけ・方向だけ・両方で `matches()` が正しい、`toQuery()` が `['port' => 5, 'dir' => 'down']` の形（null のキーは出さない）
- [ ] T014 [P] [US1] `app/tests/Service/PortFilterResolverTest.php` を作り、contracts/http-routes.md の表の全行をテストする（Request を直接作って渡す）
  - パラメータ無し・Cookie 無し → `none()`、保存の指示なし
  - パラメータ無し・Cookie あり → Cookie の条件
  - `port=5&dir=down`・Cookie `port=3` → 港5・下り、Cookie は変えない、`hasSaved` は true
  - `port=all`・Cookie あり → 全港、Cookie は変えない
  - `port=5&dir=down&save=1` → 「Cookie を書いて `/ports?port=5&dir=down` へリダイレクト」の指示
  - `port=999&dir=down&save=1` → 「書かずに `/ports?dir=down` へリダイレクト」の指示
  - `clear=1` → 「Cookie を消して `/ports` へリダイレクト」の指示
  - `port=999&dir=down`（save なし）→ 全港・下り、Cookie は変えない
  - Cookie の値が不正（存在しない港・`dir=xxx`）→ `none()`、Cookie を消す指示
  - `resolveFromCookie()`：`port=5&save=1` のクエリがあっても `redirectTo` は null で、Cookie の条件を返す。Cookie が不正なら消す指示
- [ ] T015 [P] [US1] `app/tests/View/PortBoardTest.php` に `filter()` のテストを足す：港だけ → 各方向でその港の行だけ、方向だけ → その方向だけ、両方 → 1行、`none()` → 元と同じ。日付は常に全部残る

### Implementation for User Story 1

- [ ] T016 [P] [US1] `app/src/View/PortFilter.php` を作る（`final readonly class`、data-model.md の `PortFilter`）。`portId`・`direction`・`hasSaved`、`isActive()`・`matches(RouteDirectionEnum, Port)`・`toQuery()`・`static none()`
- [ ] T017 [US1] `app/src/View/PortBoard.php` に `filter(PortFilter $filter): PortBoard` を追加する（research R5）。`PortBoardDay`・`PortBoardDirection` を作り直して、条件に合う方向・行だけを残す。条件に合う行が無い方向は落とす。日付は全部残す
- [ ] T018 [US1] `app/src/Service/PortFilterResolver.php` を作る（data-model.md の「作り方」「保存」「検証」）
  - `resolve(Request $request, list<array{direction, departurePorts, arrivalPort}> $boardStops): PortFilterResolution`
  - 戻り値の `PortFilterResolution`（同じファイルか `app/src/View/` に置く）は `filter: PortFilter`、`redirectTo: ?string`、`cookie: ?Cookie`（書くときは値入り、消すときは `Cookie::create('port_filter')->withExpires(1)`、変えないときは null）
  - `resolveFromCookie(Request $request, list<…> $boardStops): PortFilterResolution` も作る（トップ用）。クエリ（`port`・`dir`・`save`・`clear`）は見ず、Cookie だけを読む。`redirectTo` は常に null。Cookie の値が不正なら、港別ページと同じく Cookie を消す指示（`cookie`）を返す
  - 港 ID の検証は `$boardStops` の `departurePorts` の ID で行う
  - Cookie は `port_filter`、値は `http_build_query($filter->toQuery())`、有効期限 1 年、`Path=/`、`SameSite=Lax`、`HttpOnly`（data-model.md の Cookie）
- [ ] T019 [US1] `app/src/Controller/StatusController.php` の `ports()` を変える
  - `Request` を受け取り、`findBoardStops()` の結果を `PortFilterResolver::resolve()` に渡す
  - `redirectTo` があれば `RedirectResponse` を返し、`cookie` があればそれに付ける
  - 全港のボードを作ったあと `filter()` した結果を `board` として、`fullBoard`（全港）と `filter`・`boardStops` もテンプレートに渡す（`fullBoard` は Phase 4 で使う）
  - 表示のレスポンスにも `cookie`（不正な Cookie を消すとき）を付ける
  - レスポンスに `Cache-Control: private` と `Vary: Cookie` を付ける（research R15）
- [ ] T020 [US1] `app/templates/status/ports.html.twig` の上部に絞り込みフォームを置く（`method="get"`、`action="/ports"`）
  - 出発港の `<select name="port">`：「全港」（`all`）と、`boardStops` の出発港（下りの寄港順で重複なし）。今の `filter.portId` を選択済みにする
  - 方向の `<select name="dir">`：「両方向」（空）・「下り（那覇行き）」・「上り（鹿児島行き）」
  - ボタン2つ：「表示」（`save` なし）と「この港を保存」（`name="save" value="1"`）
  - JS は使わない（`onchange` での自動送信もしない。JS 無しで全機能が動くこと）
- [ ] T021 [US1] `app/templates/status/ports.html.twig` に、絞り込み中の表示を置く（FR-004）
  - `filter.isActive()` のとき「{港名}発のみ表示中」「下りのみ表示中」などと、「全港に戻す」（`/ports?port=all`）のリンク
  - `filter.hasSaved` のとき「保存を解除」（`/ports?clear=1`）のリンク
  - 絞り込みで行が無くなった**方向**は見出しも出さない。日付の `section` は常に全部出す（T034 の日付ボタンの飛び先を残すため）
- [ ] T022 [US1] `app/tests/Controller/StatusControllerTest.php` に機能テストを足す
  - `/ports?port={港ID}&dir=down` → 各日付で、その港の下りの行だけ（`li.port-row` が日数分）
  - `/ports?port={港ID}&dir=down&save=1` → 302、`Location` に `save` が無い、`Set-Cookie: port_filter=...`。続けて `/ports` → 同じ絞り込み
  - `/ports?port=all`（Cookie あり）→ 全港表示、`Set-Cookie` が無い
  - `/ports?clear=1` → 302、Cookie を消す `Set-Cookie`
  - `/ports?port=999`・`/ports?dir=xxx` → 200
  - レスポンスヘッダーに `Cache-Control` の `private` と `Vary: Cookie`

**Checkpoint**: US1 の Independent Test が通る。`make test-php` が全部通る → コミット

---

## Phase 4: User Story 2 - 欠航・条件付などの異常を最初に知る (Priority: P1)

**Goal**: 港別ページの上部に、表示期間内の欠航・条件付・遅延・運休をまとめて出す。異常の行は一覧の中でも目立たせる

**Independent Test**: 明日の名瀬発→那覇を `delayed` にしたデータで `/ports` を開くと、上部の要約に「10/2 名瀬発→那覇 ▲ 条件付・遅延」が出て、押すとその行に移動する。和泊に絞り込むと「他の港にも欠航・条件付などがあります（1件）」が出る

**依存**: US1（`PortFilter`・`fullBoard`）

### Tests for User Story 2

- [ ] T023 [P] [US2] `app/tests/Service/PortAlertSummaryBuilderTest.php` を作る
  - Cancelled・Delayed・Suspended の行が `alerts` に入る。Operating・Scheduled・NoInfo・NoService は入らない
  - 並び順が日付 → 方向（下り → 上り）→ 寄港順
  - 絞り込み中は、条件に合うものが `alerts`、合わないものの件数が `hiddenCount`
  - 異常が無く、ボードにデータがある → `alerts` 空・`hasData` true。ボードが空（`isEmpty()`）→ `hasData` false
  - `PortAlert::anchor()` が `r-2026-10-02-down-3` の形

### Implementation for User Story 2

- [ ] T024 [P] [US2] `app/src/View/PortAlert.php` と `app/src/View/PortAlertSummary.php` を作る（data-model.md）。`PortAlert::anchor()` は T011 の行の `id` と同じ形式
- [ ] T025 [US2] `app/src/Service/PortAlertSummaryBuilder.php` を作る。`build(PortBoard $fullBoard, PortFilter $filter): PortAlertSummary`。全港のボードを走査して `isAlert()` のエントリーを集め、`$filter->matches()` で `alerts` と `hiddenCount` に分ける（research R4）
- [ ] T026 [US2] `app/templates/status/_alert_summary.html.twig` を新しく作る。引数は `summary` と `linkPrefix`（港別ページでは空文字、トップでは `/ports?port=all`）
  - `alerts` があれば、各項目を「{n/j（曜）} {港}発→{到着港} {バッジ} {会社}」の1行のリンク（`href="{{ linkPrefix }}#{{ alert.anchor }}"`）にする
  - 4件以上なら最初の3件を出し、残りは `<details><summary>ほか N 件</summary>…</details>` にする（research R16）
  - `alerts` が空で `hasData` が true → 「表示期間内に欠航・条件付の便はありません」
  - `hasData` が false → 何も出さない（FR-011）
  - `hiddenCount > 0` → 「他の港にも欠航・条件付などがあります（N件）」と `/ports?port=all` へのリンク
- [ ] T027 [US2] `StatusController::ports()` で `PortAlertSummaryBuilder` を呼び、`summary` をテンプレートに渡す。`ports.html.twig` の絞り込みフォームの下に `_alert_summary` を `include` する（`linkPrefix: ''`）
- [ ] T028 [US2] 異常の行を目立たせる（FR-014、contracts/ui-status.md「異常の行」）。`_port_entry.html.twig` で `entry.isAlert()` のとき、行に `port-entry--alert` と status ごとのクラス（`--cancelled` / `--delayed` / `--suspended`）を付け、ステータスを太字にする。`base.html.twig` の `<style>` に、左の太い線（4px）と薄い背景（`--bs-danger-bg-subtle` など）を定義する
- [ ] T029 [US2] `app/tests/Controller/StatusControllerTest.php` に機能テストを足す：明日の1行を `cancelled` にして `/ports` → 要約にその港名と `href="#r-…"` のリンク、行に `port-entry--alert`。その港以外に絞り込む → 「他の港にも」と件数。異常なし → 「表示期間内に欠航・条件付の便はありません」

**Checkpoint**: US2 の Independent Test が通る。`make test-php` が全部通る → コミット

---

## Phase 5: User Story 3 - 港別の行を一目で読める (Priority: P1)

**Goal**: 行を「出港時刻とステータスが主」の2段にする。確認時刻は見出しにまとめる。日付ボタンで移動できる。出港済みは控えめ、長い詳細文は畳む。凡例を置く

**Independent Test**: 幅 375px で、各行の1段目に「{港}発 → {到着港}」「出港時刻」「ステータス」、2段目に船名／会社・着時刻が出る。確認時刻は方向の見出しに1回だけ出る。上部の日付ボタンがスクロールしても残り、押すとその日付に移動する

### Tests for User Story 3

- [ ] T030 [P] [US3] `app/tests/Controller/StatusControllerTest.php` の `testPortsShowsCheckedAt`（今は行に「時点」があることを見ている）を、方向の見出しに「{n/j H:i}時点」が1回出て、同じ時刻の行には出ないことを見るテストに直す。確認時刻が違う行だけ行に出るテストを足す
- [ ] T031 [P] [US3] `app/tests/Controller/StatusControllerTest.php` に足す：日付ボタンが4つあり `href="#d-{Y-m-d}"`、各 `section` に同じ `id`。60文字を超える詳細文は `<details>` になり、60文字以下はならない。凡例（`<details>` の中に全ステータス）がある

### Implementation for User Story 3

- [ ] T032 [US3] `app/templates/status/_port_entry.html.twig` を2段にする（FR-005・research R14）
  - 1段目（`d-flex`）：出港時刻（`H:i発`、太字）とステータスのバッジ。出港時刻が無ければバッジだけ
  - 2段目（`small text-muted`）：船名／会社、着時刻（今の `arrivalText()` のまま）、確認時刻（`entry.checkedAtDiffersFrom(commonCheckedAt)` のときだけ「{n/j H:i}時点」）
  - 行の見出し（`.fw-bold` の「{港}発 → {到着港}」）は `ports.html.twig` の `li.port-row` に残す。375px で1段目が折り返す場合は、到着港を方向の見出しに任せて行は「{港}発」だけにする
- [ ] T033 [US3] `app/templates/status/ports.html.twig` の方向の見出し（`h3`）の横に、`direction.commonCheckedAt()` があれば「{n/j H:i}時点」を出す（FR-006）
- [ ] T034 [US3] 日付ボタン（FR-007・research R3）。`ports.html.twig` のフォームの上に、表示期間の日付を「n/j（曜）」のリンク（`href="#d-…"`）で横に並べる。`base.html.twig` の `<style>` に `.date-nav { position: sticky; top: 0; z-index: 10; background: var(--bs-body-bg); }` と `section[id^="d-"], li[id^="r-"] { scroll-margin-top: <日付ボタンの高さ>; }` を足す
- [ ] T035 [US3] 出港済み（FR-008・contracts/ui-status.md）。`StatusController::ports()` で `now`（`new \DateTimeImmutable()`）を渡し、`_port_entry.html.twig` で `entry.isDeparted(now)` のとき `port-entry--departed`（不透明度 0.55）と「出港済み」の小さな文字を付ける
- [ ] T036 [US3] 長い詳細文（FR-028・research R9）。`_port_entry.html.twig` で `entry.detail|length > 60` のとき `<details><summary>{{ entry.detail|slice(0, 60) }}…</summary>{{ entry.detail }}</details>`、それ以外は今の「└ {detail}」のまま
- [ ] T037 [US6] `app/templates/status/_status_legend.html.twig` を新しく作る。`<details><summary>ステータスの見かた</summary>` の中に、contracts/ui-status.md の8種類を `_status_badge` で出し、それぞれに1行の説明を付ける（例：運航予定＝まだ運航状況が発表されていない便、情報なし＝情報を取得できていない）。`ports.html.twig` のフォームの下に `include` する（FR-026）
- [ ] T038 [US3] 幅 375 × 667 で `/ports` を目視する（quickstart PR1 の 8・9・11・13）。横スクロールが無いこと、日付ボタン・要約（3件＋ほか）・最初の行がスクロールせずに見えること。収まらなければ T032 の「行は『{港}発』だけ」に切り替え、フォームを1行にまとめる

**Checkpoint**: US3 の Independent Test が通る。`make test-php` が全部通る → コミット

---

## PR1 の仕上げ

- [ ] T039 quickstart.md の「PR1」の手順 1〜14 を全部実際に行う（ただし 13 の共通ヘッダーは PR3 なので無くてよい）
- [ ] T040 `5-ui-readability-ports` を push して PR を作る。説明に spec の US1〜3・FR-024〜026 との対応、ステータスの記号の変更（●→▲、-→■）、トップと会社別のバッジも同じ部品なので変わること、を書く

---

# PR2: トップ（`5-ui-readability-top`）

## Phase 6: User Story 4 - トップで今日の状況をつかむ (Priority: P2)

**Goal**: トップに異常の要約と、保存した港の今日の便（無ければ港別ページへのボタン）を出す。便の無い会社は縮める

**Independent Test**: Cookie なしで `/` → 要約・「自分の港の便を見る」ボタン・会社一覧。港を保存してから `/` → その港の今日の便。要約の項目は `/ports?port=all#r-…` に飛ぶ

**依存**: PR1 がマージ済み

- [ ] T041 [US4] PR1 のマージ後、`master` から `5-ui-readability-top` ブランチを切る
- [ ] T042 [US4] `StatusController::index()` を変える（research R12）
  - `findBoardStops()`・`findForBoard($today, PORT_BOARD_DAYS)` で全港4日分のボードを作る
  - `PortAlertSummaryBuilder::build($fullBoard, PortFilter::none())` で要約を作る
  - `PortFilterResolver::resolveFromCookie()`（T018）で Cookie だけを読み（クエリは見ないので、`/?port=5&save=1` でもリダイレクトしない）、`cookie` があれば（不正な Cookie を消すとき）レスポンスに付ける。保存した港があれば `$fullBoard->filter($filter)` の今日（`days[0]`）を `savedToday` として渡す。無ければ null
  - 会社一覧は今の `findTodayByAllCompanies()` のまま
  - レスポンスに `Cache-Control: private` と `Vary: Cookie` を付ける
- [ ] T043 [US4] `app/templates/status/index.html.twig` を FR-015 の順に組み直す
  1. `_alert_summary`（`linkPrefix: '/ports?port=all'`）
  2. `savedToday` があれば「{港}発の今日の便」の見出しと、`_port_entry` で各行（`now` を渡す）。その下に「この港の4日分を見る」（`/ports`）
  3. `savedToday` が無ければ、ボタン相当の大きさのリンク「自分の港の便を見る」（`/ports`、`btn btn-primary btn-lg w-100`）（FR-017）
  4. 会社一覧。航路がすべて `no_service` の会社は、カードにせず「{会社名}：本日運航なし」の1行にまとめて、カードの下に出す（FR-018）
  - 方向ごとの便の概要は出さない（FR-016）
- [ ] T044 [US4] `app/tests/Controller/StatusControllerTest.php` を直して足す
  - `testIndexLinksToPorts`（`a[href="/ports"]` が1つ）を、「自分の港の便を見る」ボタンがあることを見るテストに直す
  - Cookie なし → 要約がある、ボタンがある、「今日の便」の見出しが無い
  - Cookie `port_filter` に港 → その港の今日の行がある、ボタンが無い
  - `/?port=5&save=1` → 200（リダイレクトしない）、`Set-Cookie` が無い
  - Cookie の値が不正 → 200、ボタンが出る、Cookie を消す `Set-Cookie`
  - 要約のリンクが `/ports?port=all#r-` で始まる
  - 全航路 `no_service` の会社が「本日運航なし」の1行になり、カードにならない
  - レスポンスヘッダーに `private` と `Vary: Cookie`
  - 既存の会社カードのテスト（グリッド・カードの中身）は、運航する会社について通ること
- [ ] T045 [US4] quickstart.md の「PR2」の手順 1〜4 を実際に行い、375 × 667 で要約と保存した港の便がスクロールせずに見えることを確認する
- [ ] T046 [US4] push して PR を作る。説明に US4・FR-015〜018 との対応を書く

**Checkpoint**: US4 の Independent Test が通る。`make test-php` が全部通る → コミット

---

# PR3: 会社別ページ・共通ヘッダー・最終確認時刻（`5-ui-readability-company`）

## Phase 7: User Story 5 - 会社別ページで今日以降を見る (Priority: P2)

**Goal**: 会社別ページに今日〜3日先を、航路の要約行と便の行で出す。日付ごとに便あり・便なし・情報なしを区別する

**Independent Test**: `/company/1` で今日から順に4日分が出て、昨日以前は無い。まだ取得していない日は「情報なし」、便が無いと確認できた日は「便なし」

**依存**: PR1 がマージ済み（PR2 とは独立）

### Tests for User Story 5

- [ ] T047 [P] [US5] `app/tests/View/PortBoardTest.php` に `forCompany()` のテストを足す：その会社の Status・Scheduled のエントリーだけが残る、他社のエントリーと NoInfo・NoService のエントリーは落ちる、エントリーが無くなった行・方向は落ちる
- [ ] T048 [P] [US5] `app/tests/Repository/OperationStatusRepositoryTest.php` に `findUpcomingByCompany()` のテストを足す（今日〜3日先だけ、昨日は入らない、無効な航路は入らない）。`findRecentByCompany` のテスト2件（`testFindRecentByCompanyReturnsArray`・`testFindRecentByCompanyReturnsAtMostNDays`）を削除する

### Implementation for User Story 5

- [ ] T049 [P] [US5] `app/src/Enum/CompanyDayStateEnum.php` を作る（`Services = 'services'`、`NoService = 'no_service'`、`NoInfo = 'no_info'`）
- [ ] T050 [P] [US5] `app/src/View/CompanyDay.php` を作る（data-model.md の `CompanyDay`：`date`・`state`・`routeSummaries`・`board`）
- [ ] T051 [US5] `app/src/View/PortBoard.php` に `forCompany(int $companyId): PortBoard` を追加する（research R13）。`state` が `Status` か `Scheduled` で `companyId` が一致するエントリーだけを残す。エントリーが無くなった行、行が無くなった方向は落とす。日付は残す
- [ ] T052 [US5] `app/src/Repository/OperationStatusRepository.php` に `findUpcomingByCompany(FerryCompany $company, int $days): array` を追加する（`valid_date` が今日〜`$days-1` 日先、その会社の有効な航路。`[Y-m-d => list<OperationStatus>]`）。`findRecentByCompany()` を削除する
- [ ] T053 [US5] `app/src/Controller/StatusController.php` の `company()` を変える
  - 全港4日分のボードを作り、`forCompany($company->getId())` する
  - `findForBoard()` の結果（`DepartureStatus` の配列）から、日付ごとに「その会社の行があるか」「その会社の `no_service` の行があるか」を数える
  - 日付ごとに `CompanyDay` を作る：ボードの日付に行があれば `Services`、無くて `no_service` の行があれば `NoService`、その会社の行が1つも無ければ `NoInfo`（data-model.md の state の決め方）
  - `routeSummaries` は `findUpcomingByCompany()` のその日の行
  - `now` も渡す
- [ ] T054 [US5] `app/templates/status/company.html.twig` を書き直す（FR-019〜021）
  - 日付ごとに見出し「n月j日（曜）」
  - `routeSummaries` があれば、航路ごとに「{航路名} {バッジ} {詳細文}」の1行（詳細文は T036 と同じく60文字で畳む）
  - `state` が `Services` → 方向ごとに `_port_entry` で各行（`li.port-row` と `.fw-bold` の「{港}発 → {到着港}」）
  - `NoService` → 「— 便なし」の1行、`NoInfo` → 「？ 情報なし」の1行
- [ ] T055 [US5] `app/tests/Controller/StatusControllerTest.php` に足す：今日〜3日先の見出しが出て昨日が無い、便のある日に `li.port-row` が出る、`no_service` の行だけの日が「便なし」、行が無い日が「情報なし」、航路の要約行が出る日・出ない日。既存の `testCompanyPage*`（200・404）が通ること

**Checkpoint**: US5 の Independent Test が通る。`make test-php` が全部通る → コミット

---

## Phase 8: User Story 6 - 共通ヘッダーと最終確認時刻 (Priority: P3)

**Goal**: 全ページに共通ヘッダー（トップ・港別・各社）と最終確認時刻を出す。情報が古いときは会社名つきで警告する

**Independent Test**: 3画面すべてに同じヘッダーがあり、今いるページが分かる。1社の `checked_at` を3時間前にすると、全ページ上部に「情報が古い可能性があります」とその会社名が出る。1社の前日以降の行を消しても出る

### Tests for User Story 6

- [ ] T056 [P] [US6] `app/tests/Repository/DepartureStatusRepositoryTest.php` に `findLatestCheckedAtByCompany()` のテストを足す：会社ごとの最大値、前日より前の行は見ない、無効な会社・航路は入らない、行が無い会社はキーが無い
- [ ] T057 [P] [US6] `app/tests/Repository/` に `FerryCompanyRepositoryTest.php` を作り、`findBoardCompanies()` が「有効で、方向のある有効な航路を持つ会社」だけを返すことをテストする
- [ ] T058 [P] [US6] `app/tests/Twig/SiteExtensionTest.php` を作る（リポジトリはモック）
  - 全社の最終確認時刻が1時間前 → 古くない、表示する時刻は一番古い会社の時刻
  - 1社だけ3時間前 → 古い、その会社名が入る
  - 1社の結果が無い（キーが無い）→ 古い、その会社名が入る
  - 同じリクエストの中で2回呼んでも、リポジトリは1回しか呼ばれない

### Implementation for User Story 6

- [ ] T059 [P] [US6] `app/src/Repository/DepartureStatusRepository.php` に `findLatestCheckedAtByCompany(\DateTimeImmutable $today): array` を追加する（research R10）。`SELECT fc.id, MAX(d.checkedAt) … WHERE d.departureDate >= :from AND r.active = true AND fc.active = true AND r.direction IS NOT NULL GROUP BY fc.id`、`:from` は `$today->modify('-1 day')`。`[companyId => \DateTimeImmutable]` で返す
- [ ] T060 [P] [US6] `app/src/Repository/FerryCompanyRepository.php` に `findBoardCompanies(): array` を追加する（有効な会社で、`direction` が NULL でない有効な航路を持つもの。重複なし、ID 順）
- [ ] T061 [US6] `app/src/Twig/SiteExtension.php` を作る（`AbstractExtension`、自動で登録される）
  - `site_freshness()`：`{checkedAt: ?DateTimeImmutable, isStale: bool, staleCompanies: list<string>}`。`findBoardCompanies()` の各社について `findLatestCheckedAtByCompany()` の値を見て、無い会社と2時間以上前の会社を `staleCompanies` に入れる。`checkedAt` は値のある会社の中で一番古い時刻。閾値は `private const STALE_AFTER = 'PT2H'`
  - `site_companies()`：有効な会社の一覧（ヘッダーの「各社」用）
  - どちらも、結果をプロパティに覚えておき、同じリクエストの中では2回目以降クエリを走らせない（research R10）
- [ ] T062 [US6] `app/templates/base.html.twig` に共通ヘッダーを置く（FR-022・research R11）
  - Bootstrap の `navbar navbar-expand-md`。サイト名（`/` へのリンク）、「港別」（`/ports`）、「各社」（ドロップダウンで `site_companies()` の各社、`/company/{id}`）
  - 今いるページのリンクに `active` と `aria-current="page"`（`app.request.attributes.get('_route')` で判定）
  - スマートフォン幅では折りたたむ。ヘッダーは sticky にしない（research R16）
- [ ] T063 [US6] `app/templates/base.html.twig` のヘッダーの下に最終確認時刻を出す（FR-023）
  - 古くない → `small text-muted` で「最終確認 {n/j H:i}」
  - 古い → `alert alert-warning` で「情報が古い可能性があります（{会社名、…} の情報が2時間以上更新されていません）」と最終確認時刻
  - 3画面の「← トップへ戻る」のリンクは、共通ヘッダーがあるので削除する
- [ ] T064 [US6] `app/tests/Controller/StatusControllerTest.php` に足す：3画面すべてにヘッダー（`nav` の中に `/`・`/ports`・各社へのリンク）があり、今のページに `aria-current="page"`。テストデータの確認時刻が新しい → 警告が無い。1社の `checked_at` を3時間前にする → 警告とその会社名

**Checkpoint**: US6 の Independent Test が通る。`make test-php` が全部通る → コミット

---

## Phase 9: Polish & Cross-Cutting（PR3 の仕上げ）

- [ ] T065 幅 375 × 667 で3画面すべてを目視する（SC-008）。共通ヘッダーが入った状態で、港別ページとトップの SC-003・SC-004（スクロールせずに見える）を満たすこと。満たさなければヘッダーの高さを詰める
- [ ] T066 全ステータスを出したページをグレースケール（開発者ツールの「Emulate vision deficiencies → Achromatopsia」）で見て、記号と文言だけで区別できることを確認する（SC-007）
- [ ] T067 quickstart.md の「PR3」の手順を全部実際に行う（スクレイパーを止めてから。終わったら `make scraper-run` と `docker compose start scraper` で戻す）
- [ ] T068 push して PR を作る。説明に US5・US6 との対応、削除した `findRecentByCompany()` とそのテスト、「← トップへ戻る」を消したことを書く

---

## Dependencies & Execution Order

```
PR1（5-ui-readability-ports）
  Phase 1 Setup
     ↓
  Phase 2 Foundational（T003 → T004。T005〜T008 は T003・T004 と並行可 → T009 → T010 → T011 → T012）
     ↓
  Phase 3 US1（絞り込み）
     ↓
  Phase 4 US2（異常の要約。US1 の PortFilter を使う）
     ↓
  Phase 5 US3（行の見た目・日付ボタン・凡例）
     ↓
  PR1 マージ
     ├──────────────────────────┐
PR2（5-ui-readability-top）     PR3（5-ui-readability-company）
  Phase 6 US4                    Phase 7 US5 → Phase 8 US6 → Phase 9 Polish
```

- PR2 と PR3 は PR1 だけに依存し、互いには依存しない。ただし同時に進めると `StatusControllerTest.php` と `base.html.twig` が衝突しやすいので、順番にマージする（PR2 → PR3 を推奨）
- PR3 の T063 で「← トップへ戻る」を消すのは、PR2 のトップには無いので衝突しない
- Phase 4 の US2 は US1 の `PortFilter`・`fullBoard` を使う。Phase 5 の US3 は US1・US2 と別ファイルが多いが、`_port_entry.html.twig` と `ports.html.twig` を共有するので順番に進める

## Parallel Examples

**Phase 2**:
```
T003 companyId → T004 PortBoardEntry のメソッド（同じファイルなので順番に）
T005 commonCheckedAt / T006 lastCheckedAt
T007 PortBoardEntryTest / T008 PortBoardTest・Builder の companyId のテスト
```

**US1**:
```
T013 PortFilterTest / T014 PortFilterResolverTest / T015 filter() のテスト / T016 PortFilter
```

**US5**:
```
T047 forCompany() のテスト / T048 Repository のテスト / T049 Enum / T050 CompanyDay
```

**US6**:
```
T056・T057 Repository のテスト / T058 SiteExtension のテスト / T059・T060 Repository のメソッド
```

## Implementation Strategy

- **MVP は PR1 の Phase 3（US1）まで**：港を絞り込めるだけで、港別ページの一番大きな問題（48行の長いスクロール）が解決する。Phase 3 の Checkpoint の時点で動作確認してよい
- PR1 は US1〜US3 をまとめて1つの PR にする（港別ページの体験が揃ってから出す）。レビューが重ければ、US1 と US2・US3 で PR を分けてもよい
- 各 Phase の Checkpoint で `make test-php` を通してコミットする。テストが落ちたまま次の Phase に進まない
