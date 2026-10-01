# HTTP Routes: 運航情報画面の見やすさ改善

`POST /ports/filter`（絞り込みフォームの送信先）を追加する。`/ports` にクエリパラメータが増え、3ページとも Cookie を読む。

## GET /ports

| パラメータ | 値 | 説明 |
|---|---|---|
| `port` | 港 ID / `all` | 出発港。`all` は全港 |
| `dir` | `down` / `up` | 方向。省略で両方向 |

**GET では Cookie を書かない**（消すのは Cookie の値が不正なときだけ）。リンクや共有URLで渡した `port` / `dir` は表示だけを変える。以前の `save=1`・`clear=1` は受け付けない（無視する）。

| リクエスト | 表示 | Cookie |
|---|---|---|
| `/ports`（Cookie なし） | 全港・両方向 | 変更なし |
| `/ports`（Cookie `port=5&dir=down`） | 港5・下り | 変更なし |
| `/ports?port=5&dir=down`（Cookie `port=3`） | 港5・下り | 変更なし（港3のまま） |
| `/ports?port=all`（Cookie `port=5`） | 全港・両方向 | 変更なし（港5のまま） |
| `/ports?port=999&dir=down`（存在しない港） | 全港・下り | 変更なし |
| `/ports?port=5&save=1`・`/ports?clear=1` | `save`・`clear` は無視 | 変更なし |
| Cookie の値が不正 | 全港・両方向 | `port_filter` を消す |

- 不正な値でも 200 を返す（エラー画面にしない）
- レスポンスに `Cache-Control: private` と `Vary: Cookie` を付ける
- 日付へのアンカー：`#d-{Y-m-d}`。行へのアンカー：`#r-{Y-m-d}-{down|up}-{portId}`

## POST /ports/filter

絞り込みフォームの送信先（PR #33 レビュー）。どの操作も `GET /ports` へ **303** でリダイレクトする（PRG）。

| フィールド | 値 | 説明 |
|---|---|---|
| `action` | `show` / `save` / `clear` | 「表示」「この港を保存」「保存を解除」のボタン |
| `port` | 港 ID / `all` | 出発港 |
| `dir` | `` / `down` / `up` | 方向 |
| `_token` | CSRF トークン（ID `port_filter`） | `save`・`clear` のときだけ確かめる |

| 送信 | リダイレクト先 | Cookie |
|---|---|---|
| `action=show&port=5&dir=down` | `/ports?port=5&dir=down` | 変更なし |
| `action=show&port=all&dir=` | `/ports?port=all` | 変更なし |
| `action=save&port=5&dir=down`（トークン正） | `/ports?port=5&dir=down` | `port_filter=port=5&dir=down` を書く |
| `action=save&port=999&dir=down` | `/ports?dir=down` | 書かない（もとの Cookie は残す） |
| `action=save&port=all&dir=`（トークン正） | `/ports` | `port_filter` を消す（「全港・両方向」を保存 = 保存を消す） |
| `action=clear`（トークン正） | `/ports` | `port_filter` を消す |
| `action=save` / `clear`（トークン不正・他サイトから） | 上と同じ | 変更なし |

- CSRF トークンは Symfony の stateless トークン（`framework.csrf_protection.stateless_token_ids`）。セッションを使わず、`Sec-Fetch-Site`（無ければ `Origin` / `Referer`）が同じサイトかで確かめる。JS は要らない
- リダイレクトにも `Cache-Control: private` と `Vary: Cookie` を付ける

## GET /

- Cookie `port_filter` に港があれば、その港の**今日の**便を表示する（`dir` があればその方向だけ）
- 無ければ「自分の港の便を見る」ボタン（`/ports` へのリンク）を表示する
- 異常の要約は常に全港・4日分（Cookie では絞り込まない）。各項目のリンクは `/ports?port=all#r-...`（保存した港に関係なく行に着地でき、保存も消えない）
- レスポンスに `Cache-Control: private` と `Vary: Cookie` を付ける

## GET /company/{id}

- 表示する日付は今日〜3日先。存在しない ID は今までどおり 404
- 日付ごとに「便あり」「便なし」「情報なし」を区別する（data-model の `CompanyDay`）
