"""マルエーフェリーの状態（インスタンス変数）と、マルエーだけの読み込み。"""

from datetime import date, datetime

from sqlalchemy import select

from scraper.db.models import (
    FerryCompany,
    PortCompanyCode,
    RouteStop,
)
from scraper.scrapers.base import BaseScraper
from scraper.scrapers.marue_ferry.common import (
    SearchRow,
    ShipInfo,
    RecordedVoyage,
    ExtraParse,
)
from scraper.utils.port_notice import (
    PortNotice,
)
from scraper.utils.ports import PortResolver


class MarueState(BaseScraper):
    ROUTE_ORIGINS = ("鹿児島", "那覇")

    # fetch()・parse_departures() などで代入する（代入するまで属性は無い）
    _search_count: int
    _valid_date: date
    _searches: dict[tuple[int, int, date], list[SearchRow] | None]
    _recorded_cache: dict[tuple[str, int, datetime], RecordedVoyage]
    _stops: dict[int, list[RouteStop]]
    _resolver: PortResolver
    _ships: dict[str, ShipInfo]
    _voyage_cache: dict[tuple[str, int, date, datetime | None], ShipInfo]
    _ship_details: dict[str, str | None]
    _extra_voyages: dict[str, ExtraParse | None]
    _parse_now: datetime
    _notices: dict[str, list[PortNotice]]
    _current_voyage: dict[str, tuple[int, datetime]]
    _directions: dict[int, str]

    def __init__(self, session, company_id: int) -> None:
        # 便検索の POST は読み取り専用の検索（副作用なし）なので、429/5xx でリトライする
        super().__init__(session, company_id, retry_post=True)
        self._search_count = 0

    def _route_directions(self) -> dict[int, str]:
        if not hasattr(self, "_directions"):
            down, up = self._load_routes()
            self._directions = {
                r.id: label for r, label in ((down, "下り"), (up, "上り")) if r
            }
        return self._directions

    def _get_resolver(self) -> PortResolver:
        if not hasattr(self, "_resolver"):
            self._resolver = PortResolver.from_session(self.session)
        return self._resolver

    def _get_stops(self) -> dict[int, list[RouteStop]]:
        if not hasattr(self, "_stops"):
            self._stops = self._load_stops([r for r in self._load_routes() if r])
        return self._stops

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
