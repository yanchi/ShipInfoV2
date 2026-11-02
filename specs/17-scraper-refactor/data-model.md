# Data Model: スクレイパーを振る舞いを変えずに整理する

## DB

**変更なし**。テーブル・列・マイグレーション・`scraper/scraper/db/models.py` に触らない。書く行の中身も変えない（spec FR-001。確かめ方は research R4）。

## マルエーフェリーのインスタンスの状態（`MarueState` に宣言する）

今は `fetch()` などの中で初めて代入している属性。分けたあとも代入する場所・値は変えず、`state.py` の `MarueState` にクラスの型注釈として並べる（どの mixin から読むかが一目で分かるように）。

| 属性 | 型 | 作る場所 | 読む場所 |
|---|---|---|---|
| `_search_count` | `int` | `__init__`・`fetch` | `fetch`（`_search`） |
| `_valid_date` | `date` | `fetch` | `fetch`・`statuses`・`extra`・`ships`・`voyages` |
| `_searches` | `dict[tuple[int, int, date], list[SearchRow] \| None]` | `fetch` | `fetch`・`statuses`・`voyages`・`extra` |
| `_recorded_cache` | `dict[tuple[str, int, datetime], RecordedVoyage]` | `fetch`・`voyages` | `voyages` |
| `_stops` | `dict[int, list[RouteStop]]` | `fetch`・`state`（`_get_stops`） | `state` |
| `_resolver` | `PortResolver` | `fetch`・`state`（`_get_resolver`） | `state` |
| `_ships` | `dict[str, ShipInfo]` | `fetch` | `statuses`・`voyages`・`extra` |
| `_voyage_cache` | `dict[tuple[str, int, date, datetime \| None], ShipInfo]` | `fetch`・`voyages` | `voyages` |
| `_ship_details` | `dict[str, str \| None]` | `fetch` | `ships`・`voyages` |
| `_extra_voyages` | `dict[str, ExtraParse \| None]` | `fetch` | `extra` |
| `_parse_now` | `datetime` | `statuses`（`parse_departures`） | `extra` |
| `_notices` | `dict[str, list[PortNotice]]` | `statuses` | `voyages` |
| `_current_voyage` | `dict[str, tuple[int, datetime]]` | `statuses` | `voyages`・`extra` |
| `_directions` | `dict[int, str]` | `state`（`_route_directions`） | `state` |

- 「作る場所」「読む場所」は実装で `grep` して確かめ、違えば表を直す（表は読み手のための案内で、コードの決まりではない）
- 型注釈だけを書き、クラス属性に値を入れない（今と同じく、代入するまで属性は無い。`getattr(self, "_valid_date", ...)` のような既定値つきの読み方が今のまま効く）

## 共通にするメソッド（`BaseScraper`）

| メソッド | 戻り値 | 使う会社 |
|---|---|---|
| `_load_routes()` | `(down_route, up_route)`。`origin_port` が `ROUTE_ORIGINS[0]` なら下り、`ROUTE_ORIGINS[1]` なら上り。`active` の航路だけ。無ければ `None` | マルエー・マリックス（どちらも `ROUTE_ORIGINS = ("鹿児島", "那覇")`） |
| `_load_stops(routes)` | `route_id → list[RouteStop]`（`stop_order` 昇順）。`routes` が空なら `{}` | マルエー・マリックス |
