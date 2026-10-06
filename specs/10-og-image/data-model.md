# Data Model: OG 画像を出す

DB・Entity の変更は無い。扱うのは静的なファイル 1 つと、Twig の globals 1 つ。

## OG 画像（静的ファイル）

| 項目 | 値 |
|---|---|
| ファイル | `app/public/og-image.png` |
| URL | `/og-image.png`（head では `スキーム://ホスト/og-image.png` の絶対 URL） |
| 形式 | PNG（`image/png`） |
| 大きさ | 1200×630 |
| ファイルの大きさ | 300KB 以下 |
| 元 | `specs/10-og-image/og-image.html`（作り方は quickstart.md） |

## Twig globals（`app/config/packages/twig.yaml`）

| 名前 | 値 | 使う所 |
|---|---|---|
| `og_image_alt` | `鹿児島〜沖縄フェリー運航情報 - 青地にフェリーの絵とサイト名` | `og:image:alt` |

既存の globals（`site_name`・`og_site_name` など）は変えない。
