"""
MarueFerry (マルエーフェリー) scraper.

処理の流れ: fetch() → parse() → parse_departures()。役割ごとにファイルを分けてある
（クラスは mixin で、状態は state.py の MarueState が持つ）。

- common.py: URL・定数・dataclass・正規表現・モジュール関数
- state.py: MarueState（インスタンス変数・マルエーだけの読み込み）
- fetch.py: fetch()・便検索
- ships.py: 一覧・船の詳細の読み取り
- voyages.py: 便の特定・突き合わせ
- extra.py: 臨時便
- statuses.py: parse()（航路単位）・parse_departures()（港別）・_upsert_departures()
"""

from scraper.scrapers.marue_ferry.common import (
    KAGOSHIMA_URL,
    SEARCH_URL,
    ExtraParse,
    ExtraStop,
    ExtraVoyage,
    RecordedVoyage,
    SearchRow,
    ShipInfo,
    VoyageStatus,
)
from scraper.scrapers.marue_ferry.extra import ExtraMixin
from scraper.scrapers.marue_ferry.fetch import FetchMixin
from scraper.scrapers.marue_ferry.ships import ShipsMixin
from scraper.scrapers.marue_ferry.statuses import StatusesMixin
from scraper.scrapers.marue_ferry.voyages import VoyagesMixin

__all__ = [
    "KAGOSHIMA_URL",
    "SEARCH_URL",
    "ExtraParse",
    "ExtraStop",
    "ExtraVoyage",
    "MarueFerry",
    "RecordedVoyage",
    "SearchRow",
    "ShipInfo",
    "VoyageStatus",
]


class MarueFerry(StatusesMixin, ExtraMixin, VoyagesMixin, ShipsMixin, FetchMixin):
    pass
