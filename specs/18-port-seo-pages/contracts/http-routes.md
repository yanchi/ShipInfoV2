# HTTP Routes: 港ごとのページ

`GET /ports/{slug}` を足す。`GET /ports` の古い形（`port=<id>`）は新しい URL へ転送する。`POST /ports/filter` の移り先が変わる。
ここに書いていないことは [5-ui-readability の http-routes.md](../../5-ui-readability/contracts/http-routes.md) のまま。

## GET /ports/{slug}（新規、ルート名 `app_status_port`）

| パラメータ | 値 | 説明 |
|---|---|---|
| `slug` | `[a-z][a-z0-9-]*` | 港の URL の名前（data-model.md） |
| `dir`（クエリ） | `down` / `up` | 方向。省略・不正で両方向 |

| リクエスト | 応答 | 表示 | Cookie |
|---|---|---|---|
| `/ports/kametoku`（Cookie なし） | 200 | 亀徳・両方向 | 変更なし |
| `/ports/kametoku?dir=up`（Cookie `port=<名瀬>`） | 200 | 亀徳・上り（「保存を解除」を出す） | 変更なし |
| `/ports/kametoku?dir=xx` | 200 | 亀徳・両方向 | 変更なし |
| `/ports/xxx`・出発港の一覧に無い港 | 404 | エラーページ | 変更なし |
| Cookie の値が不正 | 200 | URL の港 | `port_filter` を消す |

- canonical・og:url は `https://<host>/ports/kametoku`（クエリを除く。今の base.html.twig の式のまま）
- `Cache-Control: private`・`Vary: Cookie`

## GET /ports（変更）

| リクエスト | 応答 |
|---|---|
| `/ports?port=<亀徳の id>` | **301** → `/ports/kametoku` |
| `/ports?port=<亀徳の id>&dir=down` | **301** → `/ports/kametoku?dir=down` |
| `/ports?port=<亀徳の id>&dir=xx` | **301** → `/ports/kametoku` |
| `/ports?port=all`・`/ports?port=all&dir=up` | 200（今までどおり） |
| `/ports?port=999`（一覧に無い番号） | 200（今までどおり。全港） |
| `/ports?dir=up`・`/ports` | 200（今までどおり。`/ports` は保存した港があればその港） |

- 301 にも `Cache-Control: private`・`Vary: Cookie` を付ける（Cookie が不正なら消す Cookie も付ける）
- 異常の要約のリンク `/ports?port=all#r-...` は変えない

## POST /ports/filter（移り先だけ変更、303 のまま）

| 送信 | リダイレクト先 |
|---|---|
| `action=show&port=<亀徳>&dir=down` | `/ports/kametoku?dir=down` |
| `action=save&port=<亀徳>&dir=`（トークン正） | `/ports/kametoku`（Cookie `port=<亀徳>` を書く） |
| `action=show&port=all&dir=up` | `/ports?dir=up` |
| `action=show&port=all&dir=` | `/ports?port=all` |
| `action=save&port=all&dir=`・`action=clear` | `/ports`（今までどおり） |

Cookie を書く・消す条件は今までどおり。

## GET /（リンクだけ変更）

- 「4日分を見る」: 保存した港があれば `/ports/{slug}`（方向の保存があれば `?dir=`）、方向だけの保存なら `/ports`
- 「自分の港の便を見る」: `/ports` のまま

## GET /sitemap.xml（追加）

今の 3 種類（トップ 1.0・港別 0.9・各社 0.8）に、出発港の一覧の順で `/ports/{slug}`（priority `0.9`）を足す。
