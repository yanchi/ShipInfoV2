# Data Model: マルエーフェリーの臨時便を港別ステータスに出す

**Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

DB のスキーマ（列・キー）は変えない。マイグレーションもなし。

## departure_statuses の使い方

| 列 | 便検索の行（今まで） | 臨時便の行（追加） |
|---|---|---|
| route_id | 方向の航路 | 見出しの方向の航路 |
| port_id | 検索した港 | 出港時刻のある港 |
| departure_date | その港の出港日 | 本文の日付 |
| ship_name | 船名 | 詳細ページの船名 |
| status | operating など | **`extra`**。抜粋が欠航・運休・条件付ならそちら（R4） |
| status_detail | 抜粋・港別情報 | 寄港しない港の文。抜粋の状態を使うときは抜粋の文 |
| scheduled_departure_at | 乗船日時 | その港の出港時刻 |
| scheduled_arrival_at | 下船日時（終点着） | 終点の入港時刻 |
| source_url | `SEARCH_URL` | **船の詳細ページの URL**（臨時便の行の目印。R5） |

- `status = 'extra'` は `departure_statuses` だけ。`operation_statuses`（ENUM）には書かない
- 臨時便の行は、`source_url` が NULL でも `SEARCH_URL` でもない行（`_is_extra_row`）

## OperationStatusEnum

| 値 | Python | PHP | label | isIrregular |
|---|---|---|---|---|
| extra | `extra = "extra"` | `Extra = 'extra'` | 臨時便 | true |

## スクレイパーの中の値（`scraper/scraper/scrapers/marue_ferry.py`）

### ExtraStop（臨時便の1港）

| 項目 | 型 | 説明 |
|---|---|---|
| port_id | int | `PortResolver.resolve()` |
| arrival_at | datetime \| None | 入港。始発港は None |
| departure_at | datetime \| None | 出港。終点は None |

### ExtraVoyage（臨時便1つ）

| 項目 | 型 | 説明 |
|---|---|---|
| ship_name | str | |
| route_id | int | 見出しの方向から |
| stops | tuple[ExtraStop, ...] | 本文の順。最後が終点（入港だけ） |
| skip_note | str \| None | 「※ …寄港いたしません。」の文 |

- 始発港の出港日：`stops[0].departure_at.date()`
- 終点の入港：`stops[-1].arrival_at`（＝各行の `scheduled_arrival_at`）

### 船ごとの読み取り結果

```
_extra_voyages: dict[str, tuple[ExtraVoyage, ...] | None]
  船名 → 臨時便のタプル（臨時便が無ければ空）
         None ＝ 詳細ページが取れなかった・status-archive が無い・読めない臨時便があった
                （この船の臨時便の行は消さない。R3・R6）
```

## 行の作り方（parse_departures の最後）

```
for ship, voyages in _extra_voyages (None は飛ばす):
  for v in voyages:
    status, detail = 抜粋に合う行の状態（cancelled/suspended/delayed）か extra（R4）
    for stop in v.stops[:-1]:                         # 終点は作らない
      key = (v.route_id, stop.port_id, stop.departure_at.date(), ship)
      if not 今日 <= key.date <= 今日 + MARUE_SEARCH_DAYS_AHEAD: continue    # FR-009
      if key が今回の便検索の記録にある:
          出港時刻が違えば、その記録の詳細に「（臨時便 HH:MM発あり）」・警告   # R7
          continue
      if DB に key の便検索の行がある: continue                           # R7
      record = {route_id, port_id, departure_date, ship_name, status, status_detail: detail,
                scheduled_departure_at: stop.departure_at,
                scheduled_arrival_at: v.stops[-1].arrival_at,
                source_url: 詳細ページ URL, freeze_after_departure: True}   # replace_scope は付けない
```

## 消し方（MarueFerry._upsert_departures）

```
super()._upsert_departures(records)
written = 今回の臨時便の行のキー
for 船 in _extra_voyages（None でない船）:
  rows = DB の臨時便の行（その船・マルエーの航路・出港日が今日〜N日先）
  便ごと（route_id, scheduled_arrival_at）にまとめる
  for 便 in 便ごと:
    if min(scheduled_departure_at) <= now: continue     # 始発港を出港済み → 全部残す
    for row in 便: if row のキー not in written: delete
```

## Base の変更（`_upsert_departures` ルール5）

```
scopes: (route_id, port_id, departure_date, source_url) → 書いた ship_name
delete where route/port/date が同じ and source_url == scope の source_url
             and ship_name not in names and 出港前
```

## 便検索の便の判定で DB を読むときの条件（R5）

`_SEARCH_ROWS = or_(DepartureStatus.source_url.is_(None), DepartureStatus.source_url == SEARCH_URL)`

`_recorded_voyages()`・`_recorded_voyage()`・`_recorded_search_keys()`・`_needs_far_search()` の WHERE に足す。

## 画面の値（PHP）

| 値 | 変更 |
|---|---|
| `PortBoardEntry::isAlert()` | Extra を足す |
| `PortBoardDay::firstExtraDepartureOf(int $companyId, RouteDirectionEnum $direction): ?PortBoardExtraDeparture` | 新規。今日その方向の Extra の便のうち、出港時刻がいちばん早いもの（港名・時刻） |
| `StatusController::index()` の `routesWithExtra` | 新規。`[routeId => PortBoardExtraDeparture]` |
