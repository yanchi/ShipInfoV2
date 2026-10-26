# Data Model: マリックスラインの臨時便を港別ステータスに出す

**Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

DB のスキーマ（列・キー）は変えない。マイグレーションもなし。状態 `extra`（臨時便）は 12-marue-extra-voyages で追加済み。

## 便の種類（research R1）

| 種類 | いつ | 航路単位（R8） | 港別 |
|---|---|---|---|
| `regular` | 詳細ページが取れて臨時便の印が無い／`fetch()` を通っていない | 今までどおり | 今までどおり |
| `extra` | 一覧に `temporary`、または詳細ページに臨時便の印 | 書かない・`seen` に入れない | 詳細ページから（R3）。取れなければ作らない（R6） |
| `unknown` | 一覧に `temporary` が無く、詳細ページが取れなかった | 一覧のクラスが読めれば控えの行（同じ日に `regular` が無いときだけ書く）。読めなければ書かない。どちらも最後に `seen` に入れる | 今までどおり予備ルート |

## departure_statuses の使い方（マリックスライン）

| 列 | 定期便の行（今まで） | 臨時便の行（追加） |
|---|---|---|
| route_id | 方向の航路 | 方向の航路（R2。名瀬発は上り） |
| port_id | 終点以外の寄港地 | 臨時便の印（`temporary`）などがある港。**`no_status` の港は作らない**（R3） |
| departure_date | その港の出港日 | 同じ |
| ship_name | 詳細ページの船名（予備ルートは `""`） | 詳細ページの船名 |
| status | 港のクラス | **`extra`**（`temporary`）。臨時便そのものの欠航などは今の対応（R3） |
| status_detail | 見出しの h4・h2 と港の説明 | 同じ（h2 は「航行経路を「那覇 → 名瀬→鹿児島」に変更し運航」など） |
| scheduled_departure_at | その港の出港 | 同じ |
| scheduled_arrival_at | 終点の入港 | 同じ |
| source_url | 定期便の詳細ページ（`/service/upstream20260907/`） | 臨時便の詳細ページ（`/service/service6731/`） |

- 臨時便が書いた行の目印は `status = 'extra'`（R5）
- 同じキーに定期便と臨時便が来たら、1本に絞る（R4・R5）。キーは今のまま

### 同じキーのときに残る行

| この回の定期便の行 | この回の臨時便の行 | DB の行 | 書く行 |
|---|---|---|---|
| 欠航・運休・抜港・不明 | あり | — | 臨時便 |
| 通常運航・条件付・航行経路変更 | あり | — | 定期便（詳細に「（臨時便 HH:MM発あり）」・警告） |
| 欠航・運休・抜港・不明 | なし | `extra`。その臨時便は今回の一覧にあるが、詳細ページを読めていない | 書かない（DB の臨時便の行を残す） |
| 欠航・運休・抜港・不明 | なし | `extra`。その臨時便が出港済み（同じ `source_url` の行のいちばん早い出港予定を過ぎている） | 書かない（DB の臨時便の行を残す） |
| 欠航・運休・抜港・不明 | なし | `extra`。上のどちらでもない（一覧から消えた未出港・出港日がずれた） | 定期便 |
| 通常運航・条件付・航行経路変更 | なし | `extra` | 定期便 |

予備ルートの行（船名なし）は、臨時便の行と同じ航路・港・出港日でも今までどおり作る（R6）。

### 臨時便の行の後始末（R7）

この回に詳細ページを読めた臨時便の URL ごとに、`source_url` がその URL で、この回にその臨時便が書かなかったキーの行を消す。消える行：

- 出港日がずれた古い日付の行
- 寄らなくなった港の行（前は寄る予定、今回は `no_status`）
- 種類が `unknown` だった回に、その URL で作った予備ルートの行（船名なし）

## operation_statuses

臨時便からは書かない（R8）。航路×日付の状態は定期便だけで決める。種類が `unknown` の便は、一覧のクラスが読めれば控えの行（同じ航路・日付に `regular` の便が無いときだけ書く）、読めなければ書かない。どちらも、その航路・日付を `no_service` にはしない。

## スクレイパーの中の値（`scraper/scraper/scrapers/marix_line.py`）

| 名前 | 中身 |
|---|---|
| `_STATUS_BY_CLASS["temporary"]` | `OperationStatusEnum.extra` |
| `_voyage_kind(block, detail_html) -> "extra" \| "regular" \| "unknown"` | R1 の表 |
| `_parse_direction(info2_text, block) -> str \| None` | R2 の順（始発港 → 一覧の欄 → 行き先） |
| `_departures_from_detail(...)` | 引数は今のまま。`voyage_status == extra` なら `no_status` の港は作らない（R3） |
| `_extra_rows_kept(route_ids, since) -> dict[key, tuple[str, datetime \| None]]` | DB の `extra` の行。キー → (`source_url`, `scheduled_departure_at`)。`parse_departures()` の頭で1回（R5） |
| `_resolve_extra_conflicts(records, kept, list_urls, read_extra_urls) -> list[dict]` | R4・R5。`list_urls` は今回の一覧の便の URL、`read_extra_urls` はこの回に詳細ページを読めた臨時便の URL |
| `_upsert_departures(records)`（Base を上書き） | Base の処理の後、flush して R7 の後始末 |

parse_departures の行（dict）に足すキー：

| キー | 型 | 説明 |
|---|---|---|
| `extra_voyage` | bool | 臨時便の詳細ページから作った行。Base は使わない（`_resolve_extra_conflicts`・`_upsert_departures` だけが見る） |

臨時便の行には `replace_source` を付けない（R7 の後始末で足りる）。

`MarixLine` のインスタンスに、`parse_departures()` から `_upsert_departures()` へ渡す値：

| 名前 | 中身 |
|---|---|
| `self._read_extra_urls: set[str]` | この回に詳細ページを読めた臨時便の URL（R7 の後始末の対象） |
| `self._dropped_regular: list[dict]` | R4・R5 で落とした定期便の行。その `replace_source` を R7 で代わりに処理する |

## 状態の流れ（9/7 上り・那覇・クロス）

```
一覧に定期便（欠航）だけ                        → 欠航（定期便の URL）
一覧に臨時便も出る                              → 臨時便（臨時便の URL）     R4
臨時便の詳細ページが取れない回                  → 臨時便のまま               R5-1
臨時便が出港した後、一覧から消える              → 臨時便のまま               R5-2
臨時便が出港する前に、一覧から消える            → 欠航（定期便の URL）       R5
臨時便の詳細ページで欠航になる                  → 欠航（臨時便の URL）       R3
```

## Base の変更（R10）

`BaseScraper._upsert_departures()`：行の書き込みの後、ルール5・6で消す前に `self.session.flush()`。結果は変わらない（本番の `autoflush=False` でも、消す行を探す SELECT がこの回の書き込みを読むようにするだけ）。
