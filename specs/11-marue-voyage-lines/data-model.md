# Data Model: 先の便にも公式の便ごとの状態を出す

**Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

DB のスキーマは変えない。`departure_statuses`・`operation_statuses` の列・キーも、書き方（`replace_scope`・`freeze_after_departure`）も今のまま。変わるのは、先の便の行の `status`・`status_detail` に値が入るようになることだけ。

## スクレイパーの中の値（`scraper/scraper/scrapers/marue_ferry.py`）

### VoyageStatus（抜粋の便の行）

| 項目 | 型 | 変更 | 説明 |
|---|---|---|---|
| departure_date | date | — | 行の日付。始発港から書いた行なら始発港の出港日 |
| direction | str | — | 「上り」「下り」 |
| status | OperationStatusEnum | — | 「臨時便運航」は operating（R4） |
| conditional | bool | — | |
| schedule_changed | bool | — | |
| from_origin | bool | **追加** | 「…発」の前が始発港（鹿児島・那覇）か。False の行だけ範囲で照合する（R7） |

### 便と行の照合（R1・R7）

```
_voyage_line(ship, route_id, origin_date, arrival_date) -> VoyageStatus | None
  direction = 航路の方向
  1. v.direction == direction and v.departure_date == origin_date        → v
  2. v.direction == direction and not v.from_origin
     and origin_date <= v.departure_date <= arrival_date                  → v
  3. None
```

### 行のステータスの決め方

| 行 | 便の行の数 | 照合 | ステータス | 詳細 |
|---|---|---|---|---|
| 今の便 | 0 | — | 船のタグ（今まで） | 今まで |
| 今の便 | 1 | 合う | 船のタグ（今まで） | 今まで |
| 今の便 | 2以上 | 合う | 行の状態 ＋ 港別情報（今まで） | 今まで |
| 今の便・出港前 | 1以上 | 合わない | **operating**（FR-011） | なし |
| 今の便・出港済み | 1以上 | 合わない | **前回記録したその便のステータス**（無ければ船のタグ） | 今まで |
| 先の便 | 0 | — | None（運航予定。今まで） | なし |
| 先の便 | 1 | 合う | **船のタグ**（全港。港別情報なし） | 抜粋（operating ならなし） |
| 先の便 | 2以上 | 合う | **行の状態**（全港。港別情報なし） | 抜粋（operating ならなし） |
| 先の便 | 1以上 | 合わない | None（運航予定。今まで） | なし |

航路単位（今日の始発港の便）は「今の便」と同じ表で決める（R6）。出港済みかどうかは、今日の始発港の行の乗船日時で決める。

### 出港済み（R7）

```
departed(origin_date, rows_of_voyage, now) =
    origin_date < today
    or min(row.departure_at for row in rows_of_voyage if row.departure_at) <= now
```

`rows_of_voyage` は、この回の検索結果のうち、同じ船・同じ航路・同じ下船日時の行。

### 前回記録したその便のステータス（R7）

```
recorded_voyage_status(ship_name, route_id, arrival_at) =
    max(_SEVERITY, [r.status for r in departure_statuses
                    if r.ship_name == ship_name and r.route_id == route_id
                    and |r.scheduled_arrival_at − arrival_at| < 24h
                    and r.status not in (None, skipped)])
    無ければ None（→ 船のタグ）
```

「同じ便」の決まりは `_recorded_voyages()` と同じ。skipped は港ごとの値なので除く。一番重いものにするのは、港ごとに分かれていた便（条件付の港と通常運航の港）を安全側でまとめるため。港別情報は今までどおり上から重ねる。

### 2日先以降の検索を足すキー（R5）

```
for ship in ships, v in ship.voyages:
    route = 方向が v.direction の航路
    for start in (v.departure_date, v.departure_date - 1日):   # 途中の港から書いた行のぶん
        for stop in stops[:-1]:
            d = start + (stop.day_offset - stops[0].day_offset)
            if today + 2日 <= d <= today + MARUE_SEARCH_DAYS_AHEAD:
                forced.add((route.id, stop.port_id, d))
```
