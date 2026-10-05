# Quickstart: V1 の見た目・ファビコン・OG を引き継ぐ

実装後の確かめ方。

## 1. 自動テスト

```bash
make test-php   # 既存のテスト（SC-006）＋この機能のテスト
make lint-php   # Twig・YAML・ルートの lint
make phpstan
make cs-php
```

この機能で足すテスト（`app/tests/Controller/`）：

- 3ページ（`/`・`/ports`・`/company/{id}`）の `<head>`：title・description・canonical・og:title・og:description・og:url・og:type・og:site_name・twitter:card の9項目（SC-002）。og:title = title、og:description = description、og:url = canonical（クエリ無し）
- 3ページの HTML に「ShipInfo」が無い。ヘッダーにサイト名、フッターに著作権表示、`<link rel="icon" href="/favicon.svg">`
- 会社別の title・description に会社名が入る
- バッジのクラスが `status-badge--{状態}`（既存テストの `.badge.bg-success` を書き換え）
- 欠航・条件付・遅延の便に注意書き、通常運航・運休の便には無い
- `GET /details/today` → 301 で `/ports`
- `GET /robots.txt`・`GET /sitemap.xml` の中身と Content-Type。sitemap に無効な会社が無い
- `createClient(['debug' => false])` で `/company/999999` → 404 で、ファビコン・サイト名・フッターがあり、「各社」メニューが無い
- GA：テスト環境では `ID` を入れても gtag が出ない（`app.environment` が `test`）

## 2. 画面で確かめる（SC-001・003・004）

```bash
make up
open http://localhost:8080/   # ポートは docker-compose.yml の nginx に合わせる
```

V1（`https://ship.isl-mentor.com/`）と並べて、375px と 1280px で次を見る。

- [ ] タブのファビコンが V1 と同じフェリーの絵
- [ ] 青い帯にサイト名（中央）、その下にナビ（トップ・港別・各社）が1行。375px でもナビが縦に積まれない
- [ ] 「各社 ▾」を開くとメニューが白地で読める。港別ページで日付ボタンの上に重なる
- [ ] 背景が薄いグレー、カードが白・角丸・影、ページの見出しに青い下線
- [ ] バッジが V1 と同じ配色の角丸。欠航・条件付の便の下に赤い注意書き
- [ ] フッターに「© 2025 鹿児島〜沖縄・奄美大島 フェリー運航情報サービス」
- [ ] 375px で横スクロールが出ない（3ページとも）
- [ ] 港別ページを下にスクロールしても、日付ボタンの後ろの内容が透けない
- [ ] 端末をダークモードにしても明るい配色のまま
- [ ] 存在しない会社（`/company/999999`）でも、ヘッダー・フッター・ファビコンが出る

エラーページを開発環境で見るには `http://localhost:8080/_error/404`（`config/routes/framework.yaml`）。

## 3. OG を確かめる（US2）

本番（または v2 のホスト）にデプロイしたあと、URL を OG の確認ツール（X の投稿画面・LINE のトーク・Facebook のシェアデバッガーなど）に入れ、サイト名・タイトル・説明文が出ることを確かめる。

## 4. 本番の切り替え（deploy/README.md に追記する内容）

1. V1 の本番の環境変数から GA の測定 ID（`GOOGLE_ANALYTICS_ID`）を確認する
2. V2 の `/opt/shipinfo-v2/.env.production` に `GOOGLE_ANALYTICS_ID=<V1 と同じ ID>` を足す（v2 のホストで並べている間は入れない。research R10）
3. 既存の「旧 ShipInfo からの切り替え」の手順で `ship.isl-mentor.com` を V2 に向ける
4. `https://ship.isl-mentor.com/details/today` が `/ports` に 301 で移ること、`/robots.txt`・`/sitemap.xml` のホストが `https://ship.isl-mentor.com` であることを確かめる
5. GA のリアルタイムレポートで計測が続いていることを確かめる
