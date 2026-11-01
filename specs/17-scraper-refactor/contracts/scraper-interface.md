# Contract: 整理の前後で変えないもの

この機能は振る舞いを変えない整理。ここに並べたものが前後で同じなら、外から見て同じとみなす（spec FR-001〜FR-003・FR-007）。

## 1. 呼び出し方

| もの | 今 | 後 |
|---|---|---|
| 登録 | `scraper/scraper/scrapers/__init__.py` の `SCRAPER_REGISTRY` に `"MarueFerry": MarueFerry`・`"MarixLine": MarixLine` | 同じ（ファイルも変えない） |
| `ferry_companies.scraper_class` | `MarueFerry`・`MarixLine` | 同じ |
| コンストラクタ | `MarueFerry(session, company_id)`・`MarixLine(session, company_id)` | 同じ |
| 入口 | `run()`（`BaseScraper`）→ `fetch()` → `parse()` → `parse_departures()` → `_upsert()`・`_upsert_departures()` | 同じ |
| `MarueFerry` の HTTP | `retry_post=True`（便検索の POST をリトライ） | 同じ |

## 2. import できる名前

```python
from scraper.scrapers.marue_ferry import (
    KAGOSHIMA_URL, SEARCH_URL,
    SearchRow, VoyageStatus, ShipInfo, RecordedVoyage,
    ExtraStop, ExtraVoyage, ExtraParse,
    MarueFerry,
)
from scraper.scrapers.marix_line import MarixLine, SOURCE_URL
from scraper.scrapers.base import BaseScraper
```

- 上は今のまま使える（`marue_ferry/__init__.py` が `__all__` で再エクスポート）
- `MarueFerry` のインスタンスから、今の名前のメソッド（`_search`・`_parse_ships`・`_extra_skips_after`・`_upsert_departures` ほか全部）が同じ引数で呼べる
- `_`（アンダースコア）で始まるモジュールの定数・関数（`_SEARCH_ROWS`・`_iso` など）は、パッケージの直下からの import を約束しない（`marue_ferry.common` から読む）。今これを外から import しているコードは無い

## 3. 書くもの

同じ入力（公式ページ・DB の状態・時刻）に対して、前後で次が同じ。

- `operation_statuses`・`departure_statuses`・`scraper_logs` の行（`id` と実行時刻の列を除く全部の列）
- `raw_html_hash`・`content_hash` の値
- 行を消す範囲（取り下げた臨時便・`replace_scope`・`unwritten_sources`）

確かめ方：research R4（[snapshot_plugin.py](../snapshot_plugin.py)・[compare_snapshots.py](../compare_snapshots.py)）。

## 4. ログと例外

- structlog の出来事の名前（`extra_voyage_unreadable`・`extra_voyage_key_conflict`・`extra_voyage_rows_deleted`・`extra_voyage_conflict`・`departure_fallback` ほか）と、そのキー
- `self._log` の `scraper` のキーは `MarueFerry`・`MarixLine`（`BaseScraper.__init__` がクラス名を使う。mixin に分けてもインスタンスのクラスは `MarueFerry` のまま）
- 例外の種類と、どこで止まるか

## 5. 変えてよいもの

- `tests/test_marue_ferry.py` の `patch()`・`monkeypatch.setattr()` の差し替え先（research R3）
- コードの置き場所（ファイル）・docstring・コメントの置き場所
