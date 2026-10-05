# HTTP Routes: V1 の見た目・ファビコン・OG を引き継ぐ

既存のルート（`/`・`/ports`・`POST /ports/filter`・`/company/{id}`）の振る舞いは変えない。HTML の `<head>` と見た目だけが変わる（[ui-theme.md](ui-theme.md)）。

追加するのは次の4つ。

## GET /favicon.svg

- 静的ファイル（`app/public/favicon.svg`、V1 と同じ内容）。nginx がそのまま返す
- `Content-Type: image/svg+xml`

## GET /details/today

V1 の URL。V2 の港別ページへ転送する（FR-017）。

| リクエスト | レスポンス |
|---|---|
| `GET /details/today` | **301** `Location: {スキーム}://{ホスト}/ports`（RedirectController が絶対 URL にする） |
| `GET /details/today?foo=1` | **301** `Location: {スキーム}://{ホスト}/ports`（クエリは捨てる） |

- `config/routes.yaml` に `Symfony\Bundle\FrameworkBundle\Controller\RedirectController`（`route: app_status_ports`・`permanent: true`・`keepQueryParams: false`）で定義する。ルート名は `app_legacy_details_today`
- `/ports` の Cookie による絞り込みはリダイレクト先でそのまま効く（転送自体は Cookie を見ない・書かない）

## GET /robots.txt

`Content-Type: text/plain; charset=UTF-8`

```text
User-agent: *
Allow: /

Sitemap: {スキーム}://{ホスト}/sitemap.xml
```

- スキーム・ホストはリクエストのもの（本番では `https://ship.isl-mentor.com`。research R6・R9）
- ルート名 `app_seo_robots`

## GET /sitemap.xml

`Content-Type: application/xml; charset=UTF-8`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url><loc>https://ship.isl-mentor.com/</loc><changefreq>hourly</changefreq><priority>1.0</priority></url>
    <url><loc>https://ship.isl-mentor.com/ports</loc><changefreq>hourly</changefreq><priority>0.9</priority></url>
    <url><loc>https://ship.isl-mentor.com/company/1</loc><changefreq>hourly</changefreq><priority>0.8</priority></url>
    <!-- 有効な会社（ferry_companies.active = 1）を ID 順に -->
</urlset>
```

- `loc` は `generateUrl(..., UrlGeneratorInterface::ABSOLUTE_URL)`。無効な会社は載せない（`/company/{id}` が 404 になるため）
- `lastmod` は出さない（V1 と同じ）
- ルート名 `app_seo_sitemap`。テンプレートは `templates/seo/sitemap.xml.twig`

## エラーページ（404・500 など）

- `templates/bundles/TwigBundle/Exception/error404.html.twig` と `error.html.twig`。`base.html.twig` を継承する
- ファビコン・ヘッダー（サイト名・「トップ」「港別」）・フッター・`<head>` のメタ情報を出す
- **DB を読まない**：ヘッダーの「各社」メニューと最終確認時刻は出さない（research R7）
- ステータスコードは今までどおり（存在しない・無効な会社 ID は 404）
