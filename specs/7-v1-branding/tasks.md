# Tasks: V1 の見た目・ファビコン・OG を引き継ぐ

**Input**: Design documents from `specs/7-v1-branding/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/http-routes.md, contracts/ui-theme.md, quickstart.md

**Tests**: 入れる。plan.md でテストファイル（`StatusControllerTest`・`SeoControllerTest`・`ErrorPageTest`）を明示していて、SC-002・SC-006 をテストで確かめるため。

**Story ラベル**: spec.md の User Story 番号（US1〜US3）。アクセス解析（FR-021・022）はどの US にも属さないので、ラベル無しの独立した Phase にする。

**PR の分け方**（plan.md「実装の分割」）: 2つの PR に分け、順番にマージする。

| PR | ブランチ | Phase | spec |
|---|---|---|---|
| PR1 | `7-v1-branding`（今のブランチ。spec・plan のコミットを含む） | Phase 1〜4 | US1・US2（FR-001〜016、FR-020） |
| PR2 | `7-v1-branding-seo`（PR1 のマージ後に `master` から切る） | Phase 5〜7 | US3（FR-017〜019）、FR-021・022、仕上げ |

**コミット**: 各 Phase の Checkpoint でコミットする（constitution V）。

**共通の注意**:
- 画面の構成・機能・ルートの振る舞いは変えない（FR-020・SC-006）。既存のテストは、見た目のクラス（`.badge.bg-success`・`.badge`）と「ShipInfo」を見ている箇所**だけ**書き換える
- `StatusControllerTest` の港別の行の探し方（`li.port-row` の中の `.fw-bold` が「{港名}発」で始まる）、`.site-header`・`.site-companies`・`.site-freshness`・`.port-entry`・`.date-nav` などのクラスは残す
- 色・寸法の値は [contracts/ui-theme.md](contracts/ui-theme.md) から写す。文言は [data-model.md](data-model.md) から写す（V1 の文言そのまま）
- 「ShipInfo」の文字列は、テンプレート・`<head>`・画面のどこにも出さない（FR-003）
- テストは `make test-php` で全部通ること。テンプレートを変えたら `make lint-php` も通すこと

---

# PR1: 見た目・ファビコン・`<head>`・エラーページ（`7-v1-branding`）

## Phase 1: Setup

- [ ] T001 `7-v1-branding` ブランチで `make up` → `make test-php` が全部通ることを確認してから始める
- [ ] T002 [P] V1 の `../ShipInfo/ship_info/public/favicon.svg` を `app/public/favicon.svg` にそのままコピーする（中身を変えない。FR-001・002、research R11）
- [ ] T003 [P] `app/config/packages/twig.yaml` に `twig.globals` を足す：`site_name`・`site_top_title`・`title_suffix`・`og_site_name`・`copyright`（値は data-model.md「サイトの固定値」の表のとおり。`title_suffix` は先頭の空白を含む ` | 鹿児島〜沖縄フェリー運航状況`）。`ga_measurement_id` は PR2（T039）で足すのでここでは足さない。`when@test` の `strict_variables: true` は残す

**Checkpoint**: ファビコンと固定文言がある。`make lint-php` が通る → コミット

---

## Phase 2: Foundational（ブロッキング前提）

**Purpose**: US1・US2 の両方が `app/templates/base.html.twig` を触るので、先に CSS の切り出しとブロックの分割を済ませる

**⚠️ CRITICAL**: この Phase が終わるまで US の実装を始めないこと

- [ ] T004 `app/templates/_site_styles.html.twig` を新しく作り、`app/templates/base.html.twig` の `<style>`〜`</style>` を中身ごと移す（`<style>` タグもパーシャル側に入れる）。base からは `{{ include('_site_styles.html.twig') }}` で読む。CSS の中身はこの時点では変えない（research R1）
- [ ] T005 `app/templates/base.html.twig` の DB を読む部分をブロックで囲む（research R7）
  - ヘッダーの `<details class="site-companies">…</details>` 全体を `{% block site_companies_menu %}…{% endblock %}` で囲む
  - 最終確認時刻と古い情報の警告（`{%- set freshness = site_freshness() -%}` から `{% endif %}` まで）を `{% block site_freshness %}…{% endblock %}` で囲む
  - `<html lang="ja">` を `<html lang="ja" data-bs-theme="light">` にする（research R2）
- [ ] T006 `make test-php` と `make lint-php` が通ることを確認する（見た目・振る舞いは変わっていないはず）

**Checkpoint**: CSS が `_site_styles.html.twig` にあり、DB を読む部品がブロックになっている。既存テストが通る → コミット

---

## Phase 3: User Story 1 - V1 と同じサイトだと分かる (Priority: P1) 🎯 MVP

**Goal**: 全ページ（トップ・港別・会社別・エラー）で、ファビコン・青いヘッダー・グレーの背景・白い角丸カード・青い下線の見出し・V1 配色のバッジ・注意書き・濃いグレーのフッターが V1 と同じテイストで出る

**Independent Test**: V1 と V2 のトップ・港別・会社別を 375px と 1280px で並べ、quickstart.md §2 のチェック項目がすべて満たされる。`make test-php` で下の T007・T008 が通る

### Tests for User Story 1

> **NOTE: 先に書いて、実装前に FAIL することを確認する**

- [ ] T007 [US1] `app/tests/Controller/StatusControllerTest.php` を直す・足す
  - 既存の書き換え：`testIndexContainsTitle` の `assertSelectorTextContains('h1', 'ShipInfo')` → `'現在の運航状況'`（research R13）。`.badge.bg-success` を見ている3か所 → `.status-badge--operating`。`testPortsShowsScheduledBadge` の `.badge` → `.status-badge--scheduled`
  - 追加 `testSiteChromeOnAllPages`：`/`・`/ports`・`/company/{有効な会社ID}` の3ページで、`.site-header .site-name` がサイト名（`鹿児島〜沖縄・奄美大島`・`フェリー運航情報` を含む）で `href="/"`、ヘッダーのナビに「トップ」「港別」「各社」がある、`footer.site-footer` の文が `© 2025 鹿児島〜沖縄・奄美大島 フェリー運航情報サービス`、`link[rel="icon"]` の `href` が `/favicon.svg`、`html` の `data-bs-theme` が `light`
  - 追加 `testCurrentPageIsMarkedInNav`：`/ports` でナビの「港別」に `aria-current="page"`、`/` で「トップ」に `aria-current="page"`
  - 追加 `testStatusWarningShownForCancelledAndDelayed`：欠航・条件付・遅延の便の行（`.port-entry`）に `.status-warning`（文言「出港時間・寄港地が変更になってる可能性があるので公式サイトをご確認ください」）があり、通常運航・運休の便の行には無い。トップの会社カードの航路の行、会社別の航路の要約行（`.route-summaries li`）でも同じ（データの作り方は既存のテストのヘルパーに合わせる）
  - 追加：「情報なし」の表示（`/` で会社が無いとき、`/ports` で情報が無いとき）が `.no-data` で出る。既存のテストでそれらのケースを作っているものがあれば、そこに assert を足す形でよい
  - 追加：3ページとも `<footer>` 要素はサイト共通の1つだけ（`footer` の数が 1）で、注記は `p.page-note`
- [ ] T008 [P] [US1] `app/tests/Controller/ErrorPageTest.php` を新しく作る（research R7）
  - `static::createClient(['debug' => false])` で `/company/999999` を開き、404・`link[rel="icon"][href="/favicon.svg"]`・`.site-header .site-name`・`footer.site-footer` があり、`.site-companies`（「各社」メニュー）と `.site-freshness` が無い。ナビは「トップ」「港別」の2つ
  - `make test-php` で T007・T008 の追加分が FAIL することを確認する

### Implementation for User Story 1

- [ ] T009 [US1] `app/templates/_site_styles.html.twig` の先頭に V1 の色・書体を足す（contracts/ui-theme.md「色・書体」）
  - `:root` に `--v1-primary`〜`--v1-warning-text` の9変数と `color-scheme: light`
  - 同じ `:root` で Bootstrap の変数を上書き：`--bs-body-bg: var(--v1-bg)`・`--bs-body-color: var(--v1-text)`・`--bs-body-font-family`（V1 の書体）・`--bs-primary: var(--v1-primary)`・`--bs-primary-rgb: 0, 115, 230`・`--bs-link-color: var(--v1-primary)`・`--bs-link-color-rgb: 0, 115, 230`
- [ ] T010 [US1] `app/templates/base.html.twig` のヘッダーを V1 の形に書き換える（FR-003・009、research R12、contracts/ui-theme.md「ヘッダー」）
  - `<header class="site-header">`（`border-bottom` は外す）の中に、サイト名 `<a class="site-name" href="{{ path('app_status_index') }}">` を中央に置く。中身は `<span>鹿児島〜沖縄・奄美大島</span> <span>フェリー運航情報</span>`（`site_name` を空白で分けて出す。`<h1>` にはしない）
  - その下の `<nav aria-label="サイト">` に「トップ」（`app_status_index`）・「港別」・`{% block site_companies_menu %}`（「各社」）の3項目を1行で中央寄せ。今いるページには `aria-current="page"` と `active`。「各社」の `<summary>` は会社別ページで `active`
  - 「ShipInfo」の文字列を消す
  - `<link rel="icon">` の data URI を `<link rel="icon" type="image/svg+xml" href="/favicon.svg">` に置き換える（FR-001）
- [ ] T011 [US1] `app/templates/_site_styles.html.twig` のヘッダーの CSS を書き換える（T010 の後）
  - `.site-header`：背景 `var(--v1-primary)`・白文字・中央・`padding`
  - `.site-name`：白・太字・下線なし・1.8rem。中の `span` は `display: inline-block`。`@media (max-width: 768px)` で 1.5rem、`@media (max-width: 480px)` で 1.25rem
  - ナビ：`display: flex; justify-content: center; flex-wrap: nowrap; gap`、リンクは白・太字・下線なし、hover と `[aria-current="page"]`・`.active` は下線。768px 以下で文字を小さく（0.9rem）
  - 「各社」の `<summary>` は白文字（今の `color: var(--bs-link-color)` を変える）。`.site-companies-menu` は白地・濃い文字・角丸＋影のまま、`z-index` を `.date-nav`（10）より上（例：30）に。中央寄せのナビからはみ出さないよう `left: 50%; transform: translateX(-50%)` などで位置を調整し、375px で画面外に出ないこと
  - 古い `.site-header .nav-link.active` などの不要になったルールは消す
- [ ] T012 [US1] `app/templates/base.html.twig` の `{% block body %}` の後（`<script>` の前）にフッター `<footer class="site-footer"><p class="mb-0">{{ copyright }}</p></footer>` を足し、`app/templates/_site_styles.html.twig` に `.site-footer`（背景 `var(--v1-footer-bg)`・白文字・中央・`padding: 1rem 0`・`margin-top: 2rem`、768px 以下で `font-size: .8rem`）を足す（FR-014）
- [ ] T013 [US1] `app/templates/_site_styles.html.twig` に本文の見た目を足す（FR-010〜012、research R14、contracts/ui-theme.md「本文」）
  - `.card`：`--bs-card-border-width: 0`・`--bs-card-border-radius: 8px`・`box-shadow: 0 2px 4px rgba(0,0,0,.1)`・白地（`--bs-card-bg: #fff`）
  - 見出し：`main h1, .page-heading, section[id^="d-"] > h2`（実装で付けたクラスに合わせる）に `border-bottom: 2px solid var(--v1-primary); padding-bottom: .5rem`
  - `.no-data`：背景 `var(--v1-bg-light)`・角丸 5px・斜体・`var(--v1-text-light)`・中央寄せ・`padding`
  - `.page-note`：小さい灰色の文字（今の `text-muted small` 相当）
  - `.date-nav` の背景は `var(--bs-body-bg)` のまま（グレーの不透明になる。Edge Cases）
- [ ] T014 [P] [US1] `app/templates/status/_status_badge.html.twig` のクラスを contracts/ui-theme.md「ステータスのバッジ」の表のとおりにする（research R3）。`badge`・`bg-*`・`badge-scheduled`・`badge-muted` を外し、`status-badge status-badge--{operating|delayed|cancelled|suspended|muted|scheduled}` にする。記号・文言・`status-none` の行は変えない
- [ ] T015 [US1] `app/templates/_site_styles.html.twig` のステータス表示の CSS を書き換える（T014 の後）
  - `.badge-scheduled`・`.badge-muted` を消し、`.status-badge`（`display: inline-block`・太字・`padding: .2rem .6rem`・`border-radius: 12px`・`font-size: .85em`・`white-space: nowrap`）と `--operating`〜`--scheduled` の背景・文字色を足す
  - 異常の行（research R4）：`.port-entry--cancelled`・`--delayed`・`--suspended` の線と背景を contracts/ui-theme.md「異常の行」の色に。`.port-entry--alert .badge` → `.port-entry--alert .status-badge`
- [ ] T016 [P] [US1] `app/templates/status/_status_warning.html.twig` を新しく作る（FR-016、research R5）。引数 `status`（`OperationStatusEnum` か null）。`status` が `cancelled` か `delayed` のときだけ `<p class="status-warning">出港時間・寄港地が変更になってる可能性があるので公式サイトをご確認ください</p>` を出す。`_site_styles.html.twig` に `.status-warning { color: var(--v1-warning-text); font-size: .85em; margin: 0 0 .3rem; }` を足す
- [ ] T017 [US1] `app/templates/status/_port_entry.html.twig` で、バッジの下に `_status_warning.html.twig` を `include` する。`entry.state` が `status` のときだけ `status: entry.status` を渡し、それ以外（運航予定・情報なし・便なし）は出さない（data-model.md「ステータスと表示の対応」）
- [ ] T018 [US1] `app/templates/status/index.html.twig` を直す
  - `<h1>` の「ShipInfo - フェリー運航情報」→「現在の運航状況」（research R13）。日付の行は今のまま
  - `<div class="alert alert-secondary">現在情報がありません。</div>` → `<div class="no-data">現在情報がありません。</div>`
  - 会社カードの航路の行（`list-group-item`）で、バッジを出す分岐のときにバッジの下に `_status_warning.html.twig`（`status: status ? status.status : null`）を出す。行のレイアウト（`d-flex justify-content-between`）が崩れないよう、航路名とバッジの行を1つの `div` にまとめ、注意書きはその下に置く
  - 下部の注記 `<footer class="text-muted small mt-4">` → `<p class="page-note mt-4">`
- [ ] T019 [P] [US1] `app/templates/status/ports.html.twig` を直す：`<div class="alert alert-secondary">港別の情報がありません。</div>` → `.no-data`、日付の `<h2>` の `border-bottom pb-1` を外して T013 の青い下線にする、下部の注記の `<footer>` → `<p class="page-note mt-4">`
- [ ] T020 [P] [US1] `app/templates/status/company.html.twig` を直す：日付の `<h2>` の `border-bottom pb-1` を外す、航路の要約行（`.route-summaries li`）のバッジの下に `_status_warning.html.twig`（`status: summary.status`）、下部の注記の `<footer>` → `<p class="page-note mt-4">`
- [ ] T021 [P] [US1] エラーページのテンプレートを新しく作る（research R7、contracts/http-routes.md「エラーページ」）
  - `app/templates/bundles/TwigBundle/Exception/error404.html.twig`：`base.html.twig` を継承。`title` は「ページが見つかりません」、`site_companies_menu`・`site_freshness` は空にする。本文は `<div class="container py-3"><h1>ページが見つかりません</h1><p>お探しのページは移動または削除された可能性があります。</p><p><a href="{{ path('app_status_index') }}">トップへ戻る</a></p></div>`
  - `app/templates/bundles/TwigBundle/Exception/error.html.twig`：同じ形で、`title`・見出しは「エラーが発生しました」、本文は「時間をおいて再度お試しください。」
  - DB を読む関数（`site_companies()`・`site_freshness()`）を呼ばないこと
- [ ] T022 [US1] `make test-php`・`make lint-php`・`make phpstan`・`make cs-php` を通す。T007・T008 が通ること、既存テストが（T007 で書き換えた箇所以外は変えずに）通ることを確認する
- [ ] T023 [US1] quickstart.md §2 の画面のチェック項目を、V1 と並べて 375px と 1280px で確かめる（タイトル・OG は US2 なのでまだ見ない）。エラーページは `http://localhost:8080/_error/404` と `/_error/500` で見る

**Checkpoint**: 全ページが V1 のテイストで出る。US1 の Acceptance Scenarios 1〜5 を満たす → コミット

---

## Phase 4: User Story 2 - SNS・チャットでシェアすると V1 と同じように表示される (Priority: P1)

**Goal**: 全ページの `<head>` に、V1 と同じ形式の title・description・canonical・OG・Twitter カードが出る

**Independent Test**: 各ページの `<head>` に SC-002 の9項目がそろい、og:title = title、og:description = description、og:url = canonical（クエリ無し）。`make test-php` で T024・T025 が通る

### Tests for User Story 2

- [ ] T024 [US2] `app/tests/Controller/StatusControllerTest.php` に足す（SC-002、quickstart.md §1）
  - `testHeadMetaOnAllPages`（データプロバイダーか3ページのループ）：`title`・`meta[name="description"]`・`link[rel="canonical"]`・`og:title`・`og:description`・`og:url`・`og:type`（`website`）・`og:site_name`（`鹿児島〜沖縄フェリー運航情報サービス`）・`twitter:card`（`summary`）の9項目がある。`og:title` = `<title>`、`og:description` = description、`og:url` = canonical。`og:image` が無い（FR-008）
  - `testTopTitleAndDescription`：`/` の `<title>` が `鹿児島〜沖縄・奄美大島フェリー運航情報`、description が data-model.md のトップの文
  - `testPageTitleFormat`：`/ports` の `<title>` が `港別運航情報 | 鹿児島〜沖縄フェリー運航状況`。`/company/{id}` の `<title>` が `{会社名} 運航状況 | 鹿児島〜沖縄フェリー運航状況` で、description に会社名を含む
  - `testCanonicalExcludesQueryString`：`/ports?port=all&dir=down` の canonical・og:url が `http://localhost/ports`（テストクライアントのホスト）
  - `testNoShipInfoAnywhere`：3ページのレスポンスの HTML 全体に `ShipInfo` が含まれない（FR-003）
- [ ] T025 [P] [US2] `app/tests/Controller/ErrorPageTest.php` に、404 の `<title>` が `ページが見つかりません | 鹿児島〜沖縄フェリー運航状況` で、description・canonical・og の9項目があり、`ShipInfo` が含まれないテストを足す

### Implementation for User Story 2

- [ ] T026 [US2] `app/templates/base.html.twig` の `<head>` を contracts/ui-theme.md「`<head>`」の順に組み直す（FR-004〜008、research R6）
  - `<title>{% block full_title %}{% block title %}{% endblock %}{{ title_suffix }}{% endblock %}</title>`（`title` は各ページで必須、トップは `full_title` ごと上書き）、`<meta name="description" content="{% block description %}…V1 の base の既定文…{% endblock %}">` の形で、ブロックを定義した場所でそのまま出す
  - og:title は `{{ block('full_title')|trim }}`、og:description は `{{ block('description')|trim }}` で同じ値を2回目に出す
  - `{%- set canonical_url = app.request.schemeAndHttpHost ~ app.request.pathInfo -%}` で canonical・og:url、og:type `website`、og:site_name `{{ og_site_name }}`、twitter:card `summary`
  - 子テンプレートのブロックの中身に改行・空白が入っても属性値が崩れないよう、子のブロックは1行で書くか `{%- -%}` で空白を詰める
- [ ] T027 [P] [US2] `app/templates/status/index.html.twig`：`title` を「現在の運航状況」、`full_title` を `{{ site_top_title }}`、`description` を data-model.md のトップの文にする
- [ ] T028 [P] [US2] `app/templates/status/ports.html.twig`：`title` を「港別運航情報」（`| ShipInfo` を消す）、`description` を data-model.md の港別の文にする
- [ ] T029 [P] [US2] `app/templates/status/company.html.twig`：`title` を `{{ company.name }} 運航状況`（`- … | ShipInfo` を消す）、`description` を data-model.md の会社別の文（会社名入り）にする
- [ ] T030 [US2] `app/templates/bundles/TwigBundle/Exception/error404.html.twig`・`error.html.twig` の `title` がそのまま `full_title` に使われることを確認する（description は既定のまま）。T021 で `title` を書いていれば変更は要らない
- [ ] T031 [US2] `make test-php`・`make lint-php`・`make phpstan`・`make cs-php` を通す。`grep -rn ShipInfo app/templates` で何も出ないことを確かめる

**Checkpoint**: 全ページの `<head>` が V1 と同じ形式。US2 の Acceptance Scenarios 1〜4 を満たす → コミット → PR1 を作る（タイトル例：`feat(app): V1 の見た目・ファビコン・OG を引き継ぐ`）。マージ後、本番（`v2.ship.isl-mentor.com`）で quickstart.md §3 の OG の確認をする

---

# PR2: V1 の URL・検索エンジン・GA・切り替え手順（`7-v1-branding-seo`）

## Phase 5: User Story 3 - V1 の URL で来た人・検索エンジンが迷わない (Priority: P2)

**Goal**: V1 の `/details/today` が `/ports` へ 301 で移り、`/robots.txt`・`/sitemap.xml` が V2 のページ構成で出る

**Independent Test**: `GET /details/today` → 301 `Location: /ports`。`GET /robots.txt`・`GET /sitemap.xml` が contracts/http-routes.md のとおり。`make test-php` で T033 が通る

- [ ] T032 [US3] PR1 のマージ後、`master` から `7-v1-branding-seo` ブランチを切る。`make test-php` が通ることを確認する

### Tests for User Story 3

- [ ] T033 [US3] `app/tests/Controller/SeoControllerTest.php` を新しく作る（contracts/http-routes.md）。データの入れ方・後片付けは `StatusControllerTest` の `setUp`・`tearDown` に合わせる
  - `testDetailsTodayRedirectsToPorts`：`GET /details/today` → 301、`Location` が `/ports`。`GET /details/today?foo=1` も `Location` が `/ports`（クエリを捨てる）
  - `testRobotsTxt`：200、`Content-Type` が `text/plain; charset=UTF-8`、本文に `User-agent: *`・`Allow: /`・`Sitemap: http://localhost/sitemap.xml`。`Disallow` が無い
  - `testSitemapXml`：200、`Content-Type` が `application/xml; charset=UTF-8`。`loc` に `http://localhost/`・`http://localhost/ports`・有効な会社の `http://localhost/company/{id}` があり、無効な会社（`active = 0`）の URL が無い。`changefreq` が `hourly`、`priority` がトップ `1.0`・港別 `0.9`・会社別 `0.8`
  - `make test-php` で FAIL することを確認する

### Implementation for User Story 3

- [ ] T034 [P] [US3] `app/config/routes.yaml` に `app_legacy_details_today`（`path: /details/today`、`controller: Symfony\Bundle\FrameworkBundle\Controller\RedirectController`、`defaults: { route: app_status_ports, permanent: true, keepQueryParams: false }`）を足す（FR-017、research R8）
- [ ] T035 [P] [US3] `app/src/Controller/SeoController.php` を新しく作る（FR-018・019、research R9）。`AbstractController` を継承し、attribute でルートを定義する
  - `#[Route('/robots.txt', name: 'app_seo_robots', methods: ['GET'])]`：`$request->getSchemeAndHttpHost() . '/sitemap.xml'` を Sitemap に入れた本文を `Response` で返す。`Content-Type: text/plain; charset=UTF-8`
  - `#[Route('/sitemap.xml', name: 'app_seo_sitemap', methods: ['GET'])]`：`FerryCompanyRepository::findActive()` で会社を取り、トップ・港別・会社別の `loc`（`generateUrl(..., UrlGeneratorInterface::ABSOLUTE_URL)`）・`changefreq`・`priority` の配列を作って `seo/sitemap.xml.twig` を描画する。`Content-Type: application/xml; charset=UTF-8`
- [ ] T036 [P] [US3] `app/templates/seo/sitemap.xml.twig` を新しく作る（contracts/http-routes.md の XML のとおり。`lastmod` は出さない）。`loc` は Twig の自動エスケープ（`.xml.twig` なので XML 用）に任せる
- [ ] T037 [US3] `make test-php`・`make lint-php`・`make phpstan`・`make cs-php` を通す。`make up` で `http://localhost:8080/robots.txt`・`/sitemap.xml`・`/details/today` を開いて確かめる（`public/` に `robots.txt`・`sitemap.xml` が無いので nginx から Symfony に回ること）

**Checkpoint**: US3 の Acceptance Scenarios 1〜3 を満たす → コミット

---

## Phase 6: アクセス解析（FR-021・022）

**Goal**: 本番かつ `GOOGLE_ANALYTICS_ID` があるときだけ、V1 と同じ gtag.js を出す。ローカル・CI では何も送らない

**Independent Test**: テスト環境の全ページに `googletagmanager.com` が無い。本番では `.env.production` に ID を入れたときだけ出る

- [ ] T038 `app/tests/Controller/StatusControllerTest.php` に `testNoAnalyticsTagOutsideProd` を足す：`/`・`/ports`・`/company/{id}` の HTML に `googletagmanager.com` と `gtag(` が含まれない（FR-022。テスト環境は `app.environment` が `test`）。`app/tests/Controller/ErrorPageTest.php` にも同じ assert を足す
- [ ] T039 `app/config/packages/twig.yaml` の `twig.globals` に `ga_measurement_id: '%env(default::GOOGLE_ANALYTICS_ID)%'` を足す（research R10。V1 の `../ShipInfo/ship_info/config/packages/twig.yaml` と同じ）
- [ ] T040 `app/templates/base.html.twig` の `</head>` の直前に、`{% if app.environment == 'prod' and ga_measurement_id %}` のときだけ V1 の `../ShipInfo/ship_info/templates/base.html.twig` と同じ gtag.js のタグ（`<script async src="https://www.googletagmanager.com/gtag/js?id=…">` と `dataLayer`・`gtag('config', …)` のインラインスクリプト）を出す。ID は `ga_measurement_id|e('url')`（URL の中）・`ga_measurement_id|e('js')`（JS の中）でエスケープする
- [ ] T041 [P] `compose.prod.yml` の `app` の `environment` に `GOOGLE_ANALYTICS_ID: ${GOOGLE_ANALYTICS_ID:-}` を足す。`deploy/.env.production.example` に `GOOGLE_ANALYTICS_ID=` を、「V1 と並べている間は空のまま。切り替えのときに V1 と同じ ID を入れる」というコメントつきで足す
- [ ] T042 `make test-php`・`make lint-php` を通す。`make verify-prod` で本番用イメージが ID 無しで起動し、HTML に gtag が出ないことを確かめる

**Checkpoint**: FR-021・022 を満たす → コミット

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T043 [P] `deploy/README.md` の「旧 ShipInfo からの切り替え」に、quickstart.md §4 の手順を足す：V1 の本番の環境変数から GA の測定 ID を確認する → V2 の `.env.production` に `GOOGLE_ANALYTICS_ID` を入れる（v2 のホストで並べている間は入れない理由も1行）→ 切り替え後に `/details/today` の 301、`/robots.txt`・`/sitemap.xml` のホストが `https://ship.isl-mentor.com` であること、GA のリアルタイムで計測が続いていることを確かめる
- [ ] T044 [P] `CLAUDE.md` の「重要な設計決定」に1行足す：サイト名・タイトル・OG の文言は V1 を引き継ぎ `app/config/packages/twig.yaml` の globals に置く（「ShipInfo」は画面に出さない）。GA は本番かつ `GOOGLE_ANALYTICS_ID` があるときだけ出す
- [ ] T045 `make test-php`・`make lint-php`・`make phpstan`・`make cs-php`・`make audit`・`make verify-prod` を全部通す
- [ ] T046 quickstart.md §2 のチェック項目を全部（375px・1280px、3ページ＋エラーページ）通しで確かめる。SC-003 用に、V1 と V2 のトップを並べたスクリーンショットを第三者 1 名に見せて「同じサイト」に見えるか確認してもらう

**Checkpoint**: PR2 の全部が終わる → コミット → PR2 を作る（タイトル例：`feat(app): V1 の URL・robots・sitemap・GA を引き継ぐ`）。マージ後、切り替えの日に deploy/README.md の手順で `ship.isl-mentor.com` を V2 に向ける

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup（Phase 1）**：すぐ始められる
- **Foundational（Phase 2）**：Phase 1 の後。US1・US2 をブロックする（どちらも `base.html.twig` を触るため）
- **US1（Phase 3）**：Phase 2 の後
- **US2（Phase 4）**：Phase 2 の後。US1 とは `<head>` と本文で触る場所が分かれているので並行もできるが、同じ `base.html.twig`・3ページのテンプレートを触るので、1人なら US1 → US2 の順が安全
- **US3（Phase 5）**：PR1 のマージ後（別ブランチ）。機能としては US1・US2 に依存しない（新しいルートだけ）
- **アクセス解析（Phase 6）**：PR1 の `base.html.twig` に足すので PR1 の後。Phase 5 とは独立
- **Polish（Phase 7）**：Phase 5・6 の後

### User Story Dependencies

- **US1（P1）**：Foundational の後。他の US に依存しない
- **US2（P1）**：Foundational の後。他の US に依存しない（テストの `testNoShipInfoAnywhere` は US1 のヘッダー・トップの h1 の書き換えが済んでいる前提なので、US1 → US2 の順で進める）
- **US3（P2）**：他の US に依存しない

### Within Each User Story

- テストを先に書き、FAIL することを確かめてから実装する
- `_site_styles.html.twig` を触るタスク（T009・T011・T012・T013・T015・T016）は同じファイルなので順番に行う
- 部品（`_status_badge`・`_status_warning`）→ 部品を使う場所（`_port_entry`・3ページ）の順

### Parallel Opportunities

- Phase 1：T002・T003
- US1：T008（ErrorPageTest）は T007 と並行。T014（`_status_badge`）・T016（`_status_warning`）は別ファイル。T019（ports）・T020（company）・T021（エラーページ）は別ファイル
- US2：T025 は T024 と並行。T027・T028・T029 は別ファイル
- US3：T034（routes.yaml）・T035（SeoController）・T036（sitemap テンプレート）は別ファイル
- Phase 7：T043・T044

---

## Parallel Example: User Story 1

```bash
# テスト（別ファイル）
Task: "T007 StatusControllerTest にヘッダー・フッター・ファビコン・バッジ・注意書きのテストを足す"
Task: "T008 ErrorPageTest を作る"

# 部品（別ファイル）
Task: "T014 _status_badge.html.twig のクラスを status-badge--{状態} にする"
Task: "T016 _status_warning.html.twig を作る"

# ページ（別ファイル。T013〜T017 の後）
Task: "T019 ports.html.twig の .no-data・h2・page-note"
Task: "T020 company.html.twig の h2・注意書き・page-note"
Task: "T021 エラーページのテンプレートを作る"
```

## Parallel Example: User Story 3

```bash
Task: "T034 routes.yaml に /details/today の 301 を足す"
Task: "T035 SeoController を作る"
Task: "T036 seo/sitemap.xml.twig を作る"
```

---

## Implementation Strategy

### MVP First（US1 のみ）

1. Phase 1・2 を終える
2. Phase 3（US1）を終える → 見た目・ファビコンが V1 と同じになる
3. **止めて確かめる**：quickstart.md §2 で V1 と並べる
4. この時点でも本番に出して問題ない（`<head>` は title だけ「ShipInfo」が残るので、PR1 は US2 まで終えてから出す）

### Incremental Delivery

1. Setup + Foundational → 土台
2. US1 → 見た目が V1 と同じ
3. US2 → `<head>` が V1 と同じ → **PR1 をマージ・デプロイ**（`v2.ship.isl-mentor.com` で OG を確認）
4. US3 + アクセス解析 + 仕上げ → **PR2 をマージ・デプロイ**
5. 切り替えの日に `.env.production` に GA の ID を入れ、`ship.isl-mentor.com` を V2 に向ける

---

## Notes

- [P] = 別ファイルで、未完了のタスクに依存しない
- V1 の「寄港地変更（青）」「スケジュール変更（紫）」のバッジは作らない（V2 に対応するステータスが無い。research R3）。spec の FR-013 に書いてあるが、V2 では delayed・cancelled に含まれる
- OG 画像・ダークモード対応・DNS の切り替え作業は範囲外（spec の Out of Scope）
