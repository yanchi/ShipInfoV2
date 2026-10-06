# Contract: `<head>` の OG・Twitter カード

全ページ（`/`・`/ports`・`/company/{id}`・エラーページ）で同じ。`{origin}` はリクエストのスキーム＋ホスト（og:url・canonical と同じ）。

## この機能で足す・変えるタグ

```html
<meta property="og:image" content="{origin}/og-image.png">
<meta property="og:image:type" content="image/png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="鹿児島〜沖縄フェリー運航情報 - 青地にフェリーの絵とサイト名">
<meta name="twitter:card" content="summary_large_image">   <!-- summary から変更 -->
```

## 変えないタグ（7-v1-branding FR-006・FR-007）

`og:title`・`og:description`・`og:url`・`og:type`（website）・`og:site_name`・`<link rel="canonical">`

## 画像

`GET /og-image.png` → 200、`Content-Type: image/png`、1200×630、300KB 以下。nginx が `public/` から静的に返す。
