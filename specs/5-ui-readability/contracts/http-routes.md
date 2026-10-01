# HTTP Routes: 運航情報画面の見やすさ改善

ルートの追加・削除は無い。`/ports` にクエリパラメータが増え、3ページとも Cookie を読む。

## GET /ports

| パラメータ | 値 | 説明 |
|---|---|---|
| `port` | 港 ID / `all` | 出発港。`all` は全港 |
| `dir` | `down` / `up` | 方向。省略で両方向 |
| `save` | `1` | 絞り込みフォームの「この港を保存」。Cookie を書いてリダイレクト |
| `clear` | `1` | 「保存を解除」。Cookie を消してリダイレクト |

**Cookie を書くのは `save=1`、消すのは `clear=1` と値が不正なときだけ。** リンクや共有URLで渡した `port` / `dir` は表示だけを変える。

| リクエスト | 表示 | Cookie |
|---|---|---|
| `/ports`（Cookie なし） | 全港・両方向 | 変更なし |
| `/ports`（Cookie `port=5&dir=down`） | 港5・下り | 変更なし |
| `/ports?port=5&dir=down`（Cookie `port=3`） | 港5・下り | 変更なし（港3のまま） |
| `/ports?port=all`（Cookie `port=5`） | 全港・両方向 | 変更なし（港5のまま） |
| `/ports?port=5&dir=down&save=1` | — | `port_filter=port=5&dir=down` を書き、`/ports?port=5&dir=down` へ 302 |
| `/ports?port=999&dir=down&save=1` | — | 書かない（もとの Cookie は残す）。`/ports?dir=down` へ 302 |
| `/ports?clear=1` | — | `port_filter` を消し、`/ports` へ 302 |
| `/ports?port=999&dir=down`（存在しない港） | 全港・下り | 変更なし |
| Cookie の値が不正 | 全港・両方向 | `port_filter` を消す |

- 不正な値でも 200 を返す（エラー画面にしない）
- レスポンスに `Cache-Control: private` と `Vary: Cookie` を付ける
- 日付へのアンカー：`#d-{Y-m-d}`。行へのアンカー：`#r-{Y-m-d}-{down|up}-{portId}`

## GET /

- Cookie `port_filter` に港があれば、その港の**今日の**便を表示する（`dir` があればその方向だけ）
- 無ければ「自分の港の便を見る」ボタン（`/ports` へのリンク）を表示する
- 異常の要約は常に全港・4日分（Cookie では絞り込まない）。各項目のリンクは `/ports?port=all#r-...`（保存した港に関係なく行に着地でき、保存も消えない）
- レスポンスに `Cache-Control: private` と `Vary: Cookie` を付ける

## GET /company/{id}

- 表示する日付は今日〜3日先。存在しない ID は今までどおり 404
- 日付ごとに「便あり」「便なし」「情報なし」を区別する（data-model の `CompanyDay`）
