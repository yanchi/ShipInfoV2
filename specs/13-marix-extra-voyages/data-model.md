# Data Model: マリックスラインの臨時便を港別ステータスに出す

**Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

DB のスキーマ（列・キー）は変えない。マイグレーションもなし。状態 `extra`（臨時便）は 12-marue-extra-voyages で追加済み。

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
| 欠航・運休・抜港・不明 | なし | `extra`（その臨時便をこの回に読めていない） | 書かない（DB の臨時便の行を残す） |
| 欠航・運休・抜港・不明 | なし | `extra`（その臨時便をこの回に読めた。出港日がずれた） | 定期便 |
| 通常運航・条件付・航行経路変更 | なし | `extra` | 定期便 |
| 予備ルートの行（船名なし） | 同じ航路・港・出港日にあり（どの船でも） | — | 書かない（R6） |
| 予備ルートの行（船名なし） | なし | 同じ航路・港・出港日に `extra` | 書かない（R6） |

臨時便の行を書いた航路・港・出港日の、船名なしの行は消す（R6）。

## operation_statuses

臨時便からは書かない（R8）。航路×日付の状態は定期便だけで決める。`seen`（同じ航路・日付の2本目を捨てる）にも臨時便を入れない。

## スクレイパーの中の値（`scraper/scraper/scrapers/marix_line.py`）

| 名前 | 中身 |
|---|---|
| `_STATUS_BY_CLASS["temporary"]` | `OperationStatusEnum.extra` |
| `_is_extra_voyage(block, detail_html) -> bool` | R1 の3つのどれか |
| `_parse_direction(info2_text, block) -> str \| None` | R2 の順（始発港 → 一覧の欄 → 行き先） |
| `_departures_from_detail(..., extra: bool)` | `extra` なら `no_status` の港は作らない（R3） |
| `_resolve_extra_conflicts(records, extra_urls) -> list[dict]` | R4・R5。`extra_urls` はこの回に詳細ページを読めた臨時便の URL |
| `_upsert_departures(records)`（Base を上書き） | Base の処理の後、臨時便の行を書いた航路・港・出港日の船名なしの行を消す（R6） |

parse_departures の行（dict）に足すキー：

| キー | 型 | 説明 |
|---|---|---|
| `extra_voyage` | bool | 臨時便の詳細ページから作った行。Base は使わない（`_resolve_extra_conflicts`・`_upsert_departures` だけが見る） |

## 状態の流れ（9/7 上り・那覇・クロス）

```
一覧に定期便（欠航）だけ        → 欠航（定期便の URL）
一覧に臨時便も出る              → 臨時便（臨時便の URL）          R4
臨時便が一覧から消える          → 臨時便のまま                    R5
臨時便の詳細ページで欠航になる  → 欠航（臨時便の URL）            R3
```
