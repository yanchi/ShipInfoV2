# Research: V1 の見た目・ファビコン・OG を引き継ぐ

**Feature**: [spec.md](spec.md) | **Date**: 2026-10-05

調査時点の現状。

- **V1**（`../ShipInfo/ship_info`）：`templates/base.html.twig` に title・description・canonical・OG・Twitter カード・GA を持つ。CSS は `public/css/styles.css`（CSS 変数で色を定義）。ファビコンは `public/favicon.svg`（32×32 の SVG）。`public/robots.txt`・`public/sitemap.xml` は静的ファイルで、ホストは `https://ship.isl-mentor.com` 決め打ち
- **V2**（`app/`）：`templates/base.html.twig` の `<style>` に共通 CSS。Bootstrap 5.3 を CDN で読む。アセットのビルド環境は無い。ファビコンは data URI の仮アイコン。`<head>` は title だけ
- **本番の配信**：コンテナの nginx は `try_files $uri /index.php`（`docker/production/app/nginx.conf`）。`public/` にあるファイルは nginx がそのまま返し、無ければ Symfony に回る
- **V2 のステータス**：`OperationStatusEnum` は operating / delayed / cancelled / suspended / unknown / no_service の6つ。V1 の「寄港地変更」「スケジュール変更」に当たる値は無い（#54 で、マリックスの航行経路変更は delayed、抜港は cancelled に寄せた）

---

## R1. CSS の置き場所と Bootstrap の扱い

**Decision**: Bootstrap 5.3 は残し、その上に V1 のテイストを重ねる。

- 色・書体は Bootstrap の CSS 変数（`--bs-body-bg`・`--bs-body-color`・`--bs-body-font-family`・`--bs-primary` など）を `:root` で上書きする
- V1 の色は `--v1-*` の CSS 変数として定義し、ヘッダー・フッター・カード・バッジから参照する（値は V1 の `styles.css` の `:root` をそのまま写す）
- CSS は `templates/_site_styles.html.twig` に切り出し、`base.html.twig` から `include` する（インラインの `<style>` のまま）

**Rationale**:
- V2 の画面は Bootstrap のクラス（`container`・`card`・`list-group`・`d-flex` など）で組んでいる。外すと全テンプレートの書き直しになり、FR-020（構成を変えない）と SC-006 のリスクが大きい。変数の上書きで済む部分が多い
- CSS が 200 行程度に増えるので base から切り出して読みやすくする。外部ファイル（`public/css/*.css`）にすると、更新時のキャッシュ破棄（バージョン付き URL）の仕組みが要る。インラインならデプロイと同時に必ず反映される。サイズも数 KB で、リクエストが1本減る分むしろ有利

**Alternatives considered**:
- V1 の `styles.css` をそのまま持ってきて Bootstrap を外す：V1 にはボード・絞り込み・要約などの部品が無く、結局書き足しになる
- `public/css/site.css` ＋ `asset()` のバージョン戦略：ビルド環境が無いので、バージョンはデプロイの SHA などを env で渡す仕組みを作ることになる。今の量では割に合わない。CSS が増えて HTML の転送量が気になったら切り替える

## R2. ダークモード

**Decision**: 明るい配色に固定する。`<html data-bs-theme="light">` と `:root { color-scheme: light; }` を付ける。

**Rationale**: spec の Edge Cases・Out of Scope のとおり。Bootstrap 5.3 は `data-bs-theme` が無ければ明るい配色だが、`color-scheme` を明示しないとフォーム部品やスクロールバーが端末のダーク設定に引きずられることがある。

## R3. ステータスのバッジ

**Decision**: `_status_badge.html.twig` の Bootstrap のクラス（`bg-success` など）を、V1 の配色の自前クラスに置き換える。記号・文言は 5-ui-readability の契約のまま。

| 状態 | V2 の記号・文言（変えない） | クラス | 配色（V1 の変数） |
|---|---|---|---|
| 通常運航 | ✓ 通常運航 | `status-badge status-badge--operating` | normal（緑） |
| 条件付・遅延 | ▲ 条件付・遅延 | `status-badge status-badge--delayed` | delayed（黄） |
| 欠航 | ✗ 欠航 | `status-badge status-badge--cancelled` | cancelled（赤） |
| 運休 | ■ 運休 | `status-badge status-badge--suspended` | suspend（グレー） |
| 情報なし・不明 | ？ 情報なし / ？ 不明 | `status-badge status-badge--muted` | no-info（薄いグレー） |
| 運航予定 | ○ 運航予定 | `status-badge status-badge--scheduled` | 白地に破線の枠（V2 にだけある状態。V1 に無いので V2 の見た目を V1 の形に合わせる） |
| 便なし | — 便なし | `status-none`（今のまま） | 灰色の文字 |

形は V1 の `.status`（角丸 12px・太字・`padding: .2rem .6rem`・`font-size: .85em`）。Bootstrap の `.badge` クラスは外す（白文字・`.75em` が V1 と違うため）。

V1 の「寄港地変更（青）」「スケジュール変更（紫）」は、**V2 に対応するステータスが無いので作らない**。V2 では航行経路変更は「条件付・遅延」、抜港は「欠航」として出る（#54）。区別して出すには DB とスクレイパーの変更が要り、spec の「見た目とサイトの名乗り方だけを変える」の範囲を超える。必要になったら別 issue で `OperationStatusEnum` に足す。

**Rationale**: クラス名を状態ごとに分けるとテストで状態を確かめやすい（今の `bg-success` を見ているテストは `status-badge--operating` に書き換える）。

**Alternatives considered**: Bootstrap の `bg-success-subtle text-success-emphasis` などで近い色にする → 色味が V1 とずれる。SC-003（同じサイトに見える）を優先して V1 の値をそのまま使う。

## R4. 異常の行の強調

**Decision**: 異常の行（`port-entry--alert`）の「左の太い線・薄い背景・太字」（5-ui-readability の FR-014）は保つ。線の色を V1 のバッジの文字色（欠航 `#721c24`・遅延 `#856404`・運休 `#383d41`）に、背景を白に近い色（バッジの背景色より薄い）にする。

**Rationale**: 行の背景をバッジの背景と同じ色にすると、行の中でバッジが埋もれる。線の色をバッジの文字色にそろえると、色の系統が V1 と一致する。

## R5. V1 の注意書き（FR-016）

**Decision**: 部品 `_status_warning.html.twig` を作り、ステータスが **欠航（cancelled）または条件付・遅延（delayed）** のとき、V1 と同じ文言・赤い小さな文字（`#c0392b`・`.85em`）で出す。出す場所は次の3つ。

- 便の行（`_port_entry.html.twig`。港別・トップの保存した港・会社別）
- トップの会社カードの航路の行
- 会社別ページの航路の要約行

**Rationale**:
- V1 の条件は「欠航・条件付・スケジュール変更・寄港地変更」。V2 ではスケジュール変更・寄港地変更は delayed / cancelled に含まれるので（R3）、2つで V1 と同じ範囲になる。運休（suspended）は V1 の条件に入っていないので出さない
- 便の行ごとに出すと港別ページで同じ文が繰り返されるが、V1 も便ごとに出しており、spec は便ごとに出すと決めている。文字は小さいので一覧性への影響は小さい

## R6. ページごとのタイトル・説明文・OG の組み立て

**Decision**: `base.html.twig` に次のブロックを置き、各ページは必要なものだけ上書きする。

| ブロック | 既定 | 上書きするページ |
|---|---|---|
| `title` | （ページ名。必須） | 全ページ |
| `full_title` | `{{ block('title') }} \| 鹿児島〜沖縄フェリー運航状況` | トップ（`鹿児島〜沖縄・奄美大島フェリー運航情報` のみ） |
| `description` | サイト共通の説明文（V1 の base の既定文） | トップ・港別・会社別 |

- `<title>`・`og:title` は `full_title`、`<meta name="description">`・`og:description` は `description` を使う（FR-006 で同じ値にする）
- canonical・og:url は `app.request.schemeAndHttpHost ~ app.request.pathInfo`（V1 と同じ。クエリ文字列を含まない）
- サイト名などの固定文言は `config/packages/twig.yaml` の `globals` に置く（`site_name`・`og_site_name`・`title_suffix`。data-model 参照）。テストと各テンプレートで同じ値を使うため

**Rationale**: V1 は `title` と `title_suffix` の2ブロックで組んでいるが、`full_title` 1つにまとめたほうが上書きの意図が読みやすい。ページ名だけ変えたいページは `title` だけ書けば済む。

**本番の URL について**: canonical・og:url は「リクエストのホスト」を使う。本番では `trusted_proxies` と `X-Forwarded-Host`・`X-Forwarded-Proto` で `https://ship.isl-mentor.com` になる（`config/packages/framework.yaml` の `when@prod`、memory: 本番の trusted_proxies と CSRF）。V1 と並べている間の `v2.ship.isl-mentor.com` では V2 のホストになるが、その vhost は `X-Robots-Tag: noindex` を付けているので検索には載らない。

**Alternatives considered**: `DEFAULT_URI` を基準にする → 開発・テストでも本番の URL が出て、ローカルで開いたページの canonical が本番を向く。リクエストのホストで十分。

## R7. エラーページ

**Decision**: `templates/bundles/TwigBundle/Exception/error.html.twig`（全ステータス共通）と `error404.html.twig` を作り、`base.html.twig` を継承する。エラーページでは DB を読む部品（ヘッダーの「各社」のメニュー、最終確認時刻）を出さない。

- `base.html.twig` の DB を読む箇所をブロック（`site_companies_menu`・`site_freshness`）で囲み、エラーページでは空にする
- 「各社」の代わりに、エラーページのナビは「トップ」「港別」だけにする

**Rationale**: 500 エラーの原因が DB の障害のとき、エラーページの描画で DB を読むと描画自体が失敗し、Symfony の素のエラーページになる（ファビコン・サイト名が出ない）。spec の Edge Cases は「少なくともファビコンとサイト名は同じ」なので、DB を読まない部分だけで組む。

**テスト**: 機能テストのクライアントは debug が有効だとデバッグ用の例外ページを出す。`static::createClient(['debug' => false])` で作って、`/company/999999` の 404 にファビコン・サイト名・フッターがあることを確かめる。

## R8. `/details/today` の転送（FR-017）

**Decision**: `config/routes.yaml` に Symfony 標準の `RedirectController` で書く。`route: app_status_ports`・`permanent: true`（301）・`keepQueryParams: false`。

**Rationale**: コードが要らない。転送先は名前で指すので、`/ports` の URL が変わっても追従する。V1 の `/details/today` にクエリは無いので捨ててよい。

**Alternatives considered**: ホストの nginx で `return 301` → V2 のテストで確かめられず、切り替え手順に設定が1つ増える。

## R9. robots.txt・sitemap.xml（FR-018・019）

**Decision**: どちらも Symfony のルート（新規 `SeoController`）で返す。`public/` に静的ファイルは置かない。

- `GET /robots.txt`：`text/plain`。`User-agent: *`・`Allow: /`・`Sitemap: {スキーム+ホスト}/sitemap.xml`。V1 の `Disallow: /contact` は V2 にページが無いので書かない
- `GET /sitemap.xml`：`application/xml`。トップ・港別・有効な会社の会社別ページ。URL は `generateUrl(..., ABSOLUTE_URL)` で作る（R6 と同じく、本番ではリクエストのホストが `https://ship.isl-mentor.com` になる）。`changefreq` は V1 と同じ `hourly`、`priority` はトップ 1.0・港別 0.9・会社別 0.8
- 会社の一覧は `FerryCompanyRepository::findActive()`（共通ヘッダーの「各社」と同じもの）を使う

**Rationale**: sitemap は有効な会社で中身が変わるので静的ファイルにできない。robots も Sitemap の行に絶対 URL が要り、V1 のように本番のホストを決め打ちすると、ローカルや v2 のホストで開いたときに本番を指してしまう。両方ルートにすれば一貫する。本番の nginx は `public/` に無いファイルを Symfony に回すので（`try_files`）、設定の変更は要らない。

**Alternatives considered**: `presta/sitemap-bundle` → ページが3種類しかなく、依存を足すほどではない。

## R10. Google Analytics（FR-021・022）

**Decision**: V1 と同じ方式にする。

- `config/packages/twig.yaml` の `globals` に `ga_measurement_id: '%env(default::GOOGLE_ANALYTICS_ID)%'`
- `base.html.twig` の `</head>` の前で、`app.environment == 'prod' and ga_measurement_id` のときだけ gtag.js を出す（V1 のコードと同じ）
- `compose.prod.yml` の app の `environment` に `GOOGLE_ANALYTICS_ID: ${GOOGLE_ANALYTICS_ID:-}` を足し、`deploy/.env.production.example` に項目を足す。値は V1 の本番の環境変数と同じ ID を、VPS の `.env.production` に手で入れる（リポジトリには書かない）
- V1 と並べている間（`v2.ship.isl-mentor.com`）は `.env.production` に ID を入れない。入れると V1 と V2 の両方の計測が同じプロパティに混ざる。切り替えのときに入れる（`deploy/README.md` の「旧 ShipInfo からの切り替え」に手順を足す）

**Rationale**: `default::` で env が無いときは空になり、ローカル・CI ではタグが出ない（FR-022）。`app.environment == 'prod'` の条件も重ねるので、ID を誤って開発の `.env` に入れても出ない。

**Alternatives considered**: GA の ID を `.env` にコミットする → 秘密ではないが、ローカルで `APP_ENV=prod` にしたときに本番の計測が汚れる。VPS でだけ入れる。

## R11. ファビコン（FR-001・002）

**Decision**: V1 の `public/favicon.svg` を `app/public/favicon.svg` にそのままコピーし、`<link rel="icon" type="image/svg+xml" href="/favicon.svg">` で参照する。nginx が静的ファイルとして返す。

**Rationale**: FR-002 で V1 と同じ URL が要る。SVG 1枚で全ブラウザのタブには足りる（V1 と同じ）。

`/favicon.ico` や `apple-touch-icon`（PNG）は V1 にも無いので作らない（spec は V1 と同じにすることが目的）。iOS のホーム画面のアイコンはページのスクリーンショットになるが、V1 と同じ挙動。

## R12. ヘッダーとナビの配置（FR-009・015）

**Decision**:

- 青い帯（`#0073e6`）の中に、サイト名（トップへのリンク、白・太字）を中央、その下にナビ（「トップ」「港別」「各社 ▾」）を中央寄せで1行
- サイト名は「鹿児島〜沖縄・奄美大島」「フェリー運航情報」の2つの `<span>`（`display: inline-block`）に分け、狭い幅ではこの境目でだけ折り返す。文字の大きさは V1 と同じ（1.8rem、768px 以下 1.5rem）。480px 以下はさらに 1.25rem にする（375px で2行に収める）
- ナビは `flex-wrap: nowrap`。3項目なので 375px でも1行に収まる（V1 の「狭い幅で縦に積む」は採らない）
- 「各社」の `<details>` のメニューは白地・濃い文字（今のまま）。開いたメニューが青い帯からはみ出すので `z-index` を日付ボタン（sticky）より上にする
- 今いるページは `aria-current="page"` と下線で示す（白文字なので、太字だけでは他の項目と区別しにくい）

**Rationale**: サイト名はページの見出し（`<h1>`）にしない。各ページに既に `<h1>`（港別運航情報 など）があり、1ページに h1 を1つにするため。見た目は V1 の `header h1` と同じ大きさ・太さにする。

## R13. 各ページの見出しとトップの h1

**Decision**:

- トップの `<h1>` は「ShipInfo - フェリー運航情報」から「現在の運航状況」に変える（FR-003：ShipInfo を出さない。V1 のトップの h2「現在の運航状況（Aライン・マリックスライン）」に合わせる）。日付の行は今のまま
- 大見出し（各ページの `<h1>` と、日付ごとの `<h2>`）に V1 の h2 と同じ青い下線（`border-bottom: 2px solid #0073e6`）を付ける。今の日付の `<h2>` の `border-bottom`（灰色）を置き換える
- 3ページの下部の「運航情報はスクレイピングにより収集しています…」は本文の注記として残し、その下にサイト共通のフッター（`<footer>`、V1 の著作権表示）を `base.html.twig` に置く。各ページの注記の `<footer>` 要素は `<p class="page-note">` に変える（ページに `<footer>` が2つ並ばないように）

## R14. カード・背景

**Decision**: Bootstrap の `.card` を V1 のカードに合わせる：白地・`border-radius: 8px`・`box-shadow: 0 2px 4px rgba(0,0,0,.1)`・枠線なし（`--bs-card-border-width: 0`）。異常の要約・凡例・日付の便の一覧・トップの会社カードはすべて `.card` なので、これだけで FR-011 を満たす。「情報なし」の表示（`.alert-secondary`）は V1 の `.no-data`（薄い背景・斜体・灰色）のクラスに置き換える。

日付ボタン（`.date-nav`）の背景は `var(--bs-body-bg)` を使っている。`--bs-body-bg` を `#f4f4f9` に上書きするので、自動的にグレーの不透明な背景になる（Edge Cases）。

---

未解決の NEEDS CLARIFICATION は無い。
