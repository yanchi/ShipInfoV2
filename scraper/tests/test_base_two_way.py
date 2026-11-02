"""
TwoWayScraper のテスト。

- ROUTE_ORIGINS を決めない具体クラスは定義した時点で TypeError
- 親（mixin）の ROUTE_ORIGINS を継げば定義できる。中間の抽象クラスは決めなくてよい
- _routes・_stops はインスタンスごとに1回だけ SELECT する（マルエー・マリックスとも）
- 同じ始発港の航路が2件以上あれば id の小さいほうを使う
- run() の頭で _reset_caches() を呼んで読み直す
"""

from datetime import datetime
from unittest.mock import patch

import pytest
import structlog
from sqlalchemy import event

from scraper.db.models import Route, RouteStop
from scraper.scrapers.base import BaseScraper, TwoWayScraper
from scraper.scrapers.marix_line import MarixLine
from scraper.scrapers.marue_ferry import MarueFerry
from tests.conftest import setup_port_master


def _concrete(**attrs):
    return {"fetch": lambda self: "", "parse": lambda self, html: [], **attrs}


class _Stub(TwoWayScraper):
    ROUTE_ORIGINS = ("鹿児島", "那覇")

    def fetch(self) -> str:
        return ""

    def parse(self, html: str) -> list[dict]:
        return []


@pytest.mark.parametrize(
    "origins",
    [None, ("鹿児島",), ("鹿児島", ""), ("鹿児島", "鹿児島"), ["鹿児島", "那覇"]],
)
def test_invalid_route_origins_raises_at_definition(origins):
    attrs = _concrete() if origins is None else _concrete(ROUTE_ORIGINS=origins)
    with pytest.raises(TypeError, match="ROUTE_ORIGINS"):
        type("_Bad", (TwoWayScraper,), attrs)


def test_route_origins_inherited_from_parent():
    class _Child(_Stub):
        pass

    assert _Child.ROUTE_ORIGINS == ("鹿児島", "那覇")


def test_abstract_intermediate_class_needs_no_route_origins():
    class _KagoshimaBase(TwoWayScraper):
        pass

    with pytest.raises(TypeError, match="ROUTE_ORIGINS"):
        type("_Bad", (_KagoshimaBase,), _concrete())
    assert type("_Ok", (_KagoshimaBase,), _concrete(ROUTE_ORIGINS=("A", "B")))


class _CountSelects:
    """Session で SELECT した ORM のクラスを数える（SQL の文字列は見ない）。"""

    def __init__(self, session):
        self.session = session
        self.mappers: list[type] = []

    def _on_execute(self, state):
        if state.is_select:
            self.mappers.extend(m.class_ for m in state.all_mappers)

    def __enter__(self):
        event.listen(self.session, "do_orm_execute", self._on_execute)
        return self

    def __exit__(self, *exc):
        event.remove(self.session, "do_orm_execute", self._on_execute)

    def count(self, cls: type) -> int:
        return self.mappers.count(cls)


@pytest.mark.parametrize(
    "scraper_cls, company_fixture",
    [(MarueFerry, "marue_ferry_company"), (MarixLine, "marix_line_company")],
)
def test_routes_and_stops_are_selected_once(
    request, db_session, scraper_cls, company_fixture
):
    company = request.getfixturevalue(company_fixture)
    setup_port_master(db_session, company)
    scraper = scraper_cls(db_session, company.id)

    with _CountSelects(db_session) as counter:
        for _ in range(3):
            down, up = scraper._routes
            stops = scraper._stops

    assert down is not None and down.origin_port == "鹿児島"
    assert up is not None and up.origin_port == "那覇"
    assert stops[down.id] and stops[up.id]
    assert counter.count(Route) == 1
    assert counter.count(RouteStop) == 1


def test_duplicate_origin_uses_smallest_id(db_session, marue_ferry_company):
    first, _ = MarueFerry(db_session, marue_ferry_company.id)._routes
    db_session.add(
        Route(
            ferry_company_id=marue_ferry_company.id,
            name="鹿児島〜那覇（季節便）",
            origin_port="鹿児島",
            destination_port="那覇",
            active=True,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
    )
    db_session.flush()

    with structlog.testing.capture_logs() as logs:
        down, _ = MarueFerry(db_session, marue_ferry_company.id)._routes

    assert down.id == first.id
    warnings = [e for e in logs if e["event"] == "route_ambiguous"]
    assert len(warnings) == 1
    assert warnings[0]["origin_port"] == "鹿児島"
    assert warnings[0]["used"] == first.id
    assert len(warnings[0]["route_ids"]) == 2


def test_reset_caches_reloads(db_session, marue_ferry_company):
    scraper = MarueFerry(db_session, marue_ferry_company.id)
    down, _ = scraper._routes
    assert down.id in scraper._directions

    down.active = False
    db_session.flush()
    scraper._reset_caches()

    assert scraper._routes[0] is None
    assert down.id not in scraper._directions


def test_run_resets_caches(db_session, marue_ferry_company):
    scraper = MarueFerry(db_session, marue_ferry_company.id)
    down, _ = scraper._routes

    down.active = False
    db_session.flush()
    with patch.object(BaseScraper, "run"):  # fetch() 以降は動かさない
        scraper.run()

    assert scraper._routes[0] is None
