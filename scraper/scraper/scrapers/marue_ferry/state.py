"""マルエーフェリーの状態（インスタンス変数）と、マルエーだけの読み込み。

fetch・ships・voyages・extra・statuses の mixin は、互いのメソッドを self. で呼ぶ。
mixin を1つだけ使わず、必ず MarueFerry（__init__.py）で全部組んで使うこと。
"""

from datetime import date, datetime
from functools import cached_property

from sqlalchemy import select

from scraper.db.models import (
    FerryCompany,
    PortCompanyCode,
)
from scraper.scrapers.base import TwoWayScraper
from scraper.scrapers.marue_ferry.common import (
    SearchRow,
    ShipInfo,
    RecordedVoyage,
    ExtraParse,
)
from scraper.scrapers.routes import AMAMI_ROUTE_ORIGINS
from scraper.utils.port_notice import (
    PortNotice,
)


class MarueState(TwoWayScraper):
    ROUTE_ORIGINS = AMAMI_ROUTE_ORIGINS

    # fetch()・parse_departures() などで代入する（代入するまで属性は無い）
    _search_count: int
    _valid_date: date
    _searches: dict[tuple[int, int, date], list[SearchRow] | None]
    _recorded_cache: dict[tuple[str, int, datetime], RecordedVoyage]
    _ships: dict[str, ShipInfo]
    _voyage_cache: dict[tuple[str, int, date, datetime | None], ShipInfo]
    _ship_details: dict[str, str | None]
    _extra_voyages: dict[str, ExtraParse | None]
    _parse_now: datetime
    _notices: dict[str, list[PortNotice]]
    _current_voyage: dict[str, tuple[int, datetime]]

    def __init__(self, session, company_id: int) -> None:
        # 便検索の POST は読み取り専用の検索（副作用なし）なので、429/5xx でリトライする
        super().__init__(session, company_id, retry_post=True)
        self._search_count = 0

    @cached_property
    def _directions(self) -> dict[int, str]:
        """route_id → 「下り」「上り」。"""
        down, up = self._routes
        return {r.id: label for r, label in ((down, "下り"), (up, "上り")) if r}

    def _load_port_codes(self) -> dict[int, str]:
        rows = (
            self.session.execute(
                select(PortCompanyCode).where(
                    PortCompanyCode.ferry_company_id == self.company_id
                )
            )
            .scalars()
            .all()
        )
        return {r.port_id: r.external_code for r in rows}

    def _marix_company_id(self) -> int | None:
        return self.session.execute(
            select(FerryCompany.id).where(FerryCompany.scraper_class == "MarixLine")
        ).scalar()
