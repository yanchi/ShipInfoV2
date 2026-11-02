"""
TwoWayScraper のテスト。

- ROUTE_ORIGINS を決めないサブクラスは定義した時点で TypeError
- 親（mixin）の ROUTE_ORIGINS を継げば定義できる
- _routes・_stops はインスタンスごとに1回だけ SELECT する
"""

import pytest
from sqlalchemy import event

from scraper.scrapers.base import TwoWayScraper
from scraper.scrapers.marue_ferry import MarueFerry
from tests.conftest import setup_port_master


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
    attrs = {} if origins is None else {"ROUTE_ORIGINS": origins}
    with pytest.raises(TypeError, match="ROUTE_ORIGINS"):
        type("_Bad", (TwoWayScraper,), attrs)


def test_route_origins_inherited_from_parent():
    class _Child(_Stub):
        pass

    assert _Child.ROUTE_ORIGINS == ("鹿児島", "那覇")


def test_routes_and_stops_are_selected_once(db_session, marue_ferry_company):
    setup_port_master(db_session, marue_ferry_company)
    scraper = MarueFerry(db_session, marue_ferry_company.id)

    statements: list[str] = []

    def count(conn, cursor, statement, *args):
        statements.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", count)
    try:
        for _ in range(3):
            down, up = scraper._routes
            stops = scraper._stops
            scraper._route_directions()
    finally:
        event.remove(engine, "before_cursor_execute", count)

    assert down is not None and down.origin_port == "鹿児島"
    assert up is not None and up.origin_port == "那覇"
    assert stops[down.id] and stops[up.id]
    assert sum("FROM routes" in s for s in statements) == 1
    assert sum("FROM route_stops" in s for s in statements) == 1
