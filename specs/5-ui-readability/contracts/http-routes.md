# HTTP Routes: 運航情報画面の見やすさ改善

ルートの追加・削除は無い。`/ports` にクエリパラメータが増え、3ページとも Cookie を読む。

## GET /ports

| パラメータ | 値 | 説明 |
|---|---|---|
| `port` | 港 ID / `all` | 出発港。`all` は全港にして Cookie を消す |
| `dir` | `down` / `up` | 方向。省略で両方向 |

| リクエスト | 表示 | Cookie |
|---|---|---|
| `/ports`（Cookie なし） | 全港・両方向 | 変更なし |
| `/ports`（Cookie `port=5&dir=down`） | 港5・下り | 変更なし |
| `/ports?port=5&dir=down` | 港5・下り | `port_filter=port=5&dir=down` を書く |
| `/ports?port=all` | 全港・両方向 | `port_filter` を消す |
| `/ports?port=999`（存在しない港） | 全港（`dir` があればその方向） | 書かない |
| Cookie の値が不正 | 全港・両方向 | `port_filter` を消す |

- 不正な値でも 200 を返す（エラー画面にしない）
- 日付へのアンカー：`#d-{Y-m-d}`。行へのアンカー：`#r-{Y-m-d}-{down|up}-{portId}`

## GET /

- Cookie `port_filter` に港があれば、その港の**今日の**便を表示する（`dir` があればその方向だけ）
- 無ければ「自分の港の便を見る」ボタン（`/ports` へのリンク）を表示する
- 異常の要約は常に全港・4日分（Cookie では絞り込まない）

## GET /company/{id}

- 表示する日付は今日〜3日先。存在しない ID は今までどおり 404
