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
| from_midway | bool | **追加** | 最後の「発」より前を `PortResolver.resolve()` で引いた港が、行の方向の航路の途中の港（`route_stops` の始発・終点以外）か。True の行だけ範囲で照合する（R7） |

### 便と行の照合（R1・R7）

```
_voyage_line(ship, route_id, origin_date, arrival_date) -> VoyageStatus | None
  direction = 航路の方向
  1. v.direction == direction and v.departure_date == origin_date        → v
  2. v.direction == direction and v.from_midway
     and origin_date <= v.departure_date <= arrival_date                  → v
  3. None
```

### 行のステータスの決め方

| 行 | 便の行の数 | 照合 | ステータス | 詳細 |
|---|---|---|---|---|
| 今の便 | 0 | — | 船のタグ（今まで） | 今まで |
| 今の便 | 1 | 合う | 船のタグ（今まで） | 今まで |
| 今の便 | 2以上 | 合う | 行の状態 ＋ 港別情報（今まで） | 今まで |
| 今の便・出港前 | 1以上 | 合わない・タグ ≦ 行の一番重いもの・（タグに条件付があれば条件付の行あり） | **operating**（FR-011）。`assumed_operating=True` で港別情報を当てない | なし |
| 今の便・出港前 | 1以上 | 合わない・タグ ＞ 行の一番重いもの、またはタグに条件付があるのに条件付の行なし | 船のタグ＋`voyage_tag_heavier_than_lines` | 今まで |
| 今の便・出港済み | 1以上 | 合わない | **前回記録したその港の行のステータス**（無ければその便で一番重いもの、それも無ければ船のタグ）。`use_recorded=True` で港別情報を当てない | 前回の行の詳細（今の抜粋は他の便の話なので使わない） |
| 今の便・出港済み | 1以上 | 合わない・安全装置に当たる（上の2行のタグが重い／条件付の行なし） | まだ出港していない港は**船のタグ**＋港別情報、出港済みの港は前回の記録（`tag_over_recorded=True`）。航路単位は船のタグ | 今まで／前回の行の詳細 |
| 先の便 | 0 | — | None（運航予定。今まで） | なし |
| 先の便 | 1 | 合う | **船のタグ**（全港。港別情報なし） | 抜粋（operating ならなし） |
| 先の便 | 2以上 | 合う | **行の状態**（全港。港別情報なし） | 抜粋（operating ならなし） |
| 先の便 | 1以上 | 合わない | None（運航予定。今まで） | なし |

航路単位（今日の始発港の便）は「今の便」と同じ表で決める（R6）。出港済みかどうかは、今日の始発港の行の乗船日時で決める。

### 出港済み（R7）

```
departed(origin_date, voyage, now) =
    origin_date < today
    or min(departure_at of rows_of_voyage ∪ recorded_rows_of_voyage) <= now
```

- `rows_of_voyage`：この回の検索結果のうち、同じ船・同じ航路・同じ下船日時の行の乗船日時
- `recorded_rows_of_voyage`：DB の `departure_statuses` のうち、同じ船・同じ航路で下船日時の差が24時間未満の行の `scheduled_departure_at`（始発港のキーの検索が失敗した回でも判定できるように。M3）

### 前回記録したその便のステータス（R7）

DB は今の便ごとに1回だけ引き（`ship_name`・`route_id`・`scheduled_arrival_at` の差が24時間未満）、`(port_id, departure_date) → (status, status_detail)` と `scheduled_departure_at` を持っておく。

```
recorded_port_status(voyage, port_id, d) =
    その便の (port_id, d) の行があり status が NULL でなければ (status, status_detail)   # 港ごとにそのまま
recorded_voyage_status(voyage) =
    max(_SEVERITY, [r.status for r in その便の行 if r.status not in (None, skipped, unknown)])
    無ければ None
```

- 航行中に抜港している港：前回の行が `skipped` なら、検索結果が0件でも `skipped`（時刻なし）の行を保つ
- 港の行（`parse_departures()`）：`recorded_port_status` → 無ければ `recorded_voyage_status`（詳細は抜粋）→ 無ければ船のタグ
- 航路単位（`_route_status()`）：`recorded_voyage_status` → 無ければ船のタグ
- `use_recorded` のときは、前回の行が無い港（`ship.status` と抜粋に戻る道）も含めて、港別情報を一切見ない。`_skipped_on_current_voyage()` も抜港の行を作らない（4回目の analyze M4）
- 「同じ便」の決まりは `_recorded_voyages()` と同じ。港ごとにそのまま使うので、条件付の便で港ごとに分かれていた状態（言及の無い港は operating）が出港後も崩れない

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

DB の行による追加（行が消えたとき。R5）:

```
forced |= {(r.route_id, r.port_id, r.departure_date)
           for r in departure_statuses
           if r.route_id in マルエーの航路 and r.ship_name != ""
           and r.status in (cancelled, suspended, delayed, operating)
           and today + 2日 <= r.departure_date <= today + MARUE_SEARCH_DAYS_AHEAD}
```
