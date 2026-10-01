"""
BaseScraper の港別処理（parse_departures / _upsert_departures / run）のテスト。

data-model.md の更新ルール1〜5・7 を確認する。
"""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from scraper.db.models import (
    DepartureStatus,
    FerryCompany,
    OperationStatus,
    OperationStatusEnum,
    Port,
    Route,
    ScraperLog,
    ScraperStatusEnum,
)
from scraper.scrapers.base import BaseScraper


class _StubScraper(BaseScraper):
    """parse / parse_departures の戻り値を外から差し替えられるスタブ。"""

    route_records: list[dict] = []
    departure_records: list[dict] | Exception = []

    def fetch(self) -> str:
        return "<html/>"

    def parse(self, html: str) -> list[dict]:
        return self.route_records

    def parse_departures(self) -> list[dict]:
        if isinstance(self.departure_records, Exception):
            raise self.departure_records
        return self.departure_records


@pytest.fixture
def setup(db_session):
    company = FerryCompany(name="テスト会社", scraper_class="_StubScraper", active=True)
    db_session.add(company)
    db_session.flush()
    route = Route(
        ferry_company_id=company.id,
        name="テスト航路",
        origin_port="鹿児島",
        destination_port="那覇",
        direction="down",
        active=True,
    )
    port = Port(name="名瀬", aliases=["名瀬港", "名瀬"])
    db_session.add_all([route, port])
    db_session.commit()
    scraper = _StubScraper(db_session, company.id)
    return scraper, company, route, port


def _rec(route, port, **kw):
    rec = {
        "route_id": route.id,
        "port_id": port.id,
        "departure_date": date.today(),
        "ship_name": "フェリーあけぼの",
        "status": OperationStatusEnum.operating,
        "status_detail": None,
        "scheduled_departure_at": datetime.now() + timedelta(hours=3),
        "scheduled_arrival_at": datetime.now() + timedelta(hours=10),
        "source_url": "https://example.com/",
    }
    rec.update(kw)
    return rec


def _rows(db_session):
    return db_session.execute(select(DepartureStatus)).scalars().all()


def _age(row, hours=2):
    """行の時刻を過去にずらして、更新されたかを見分けられるようにする。"""
    old = datetime.now() - timedelta(hours=hours)
    row.checked_at = old
    row.scraped_at = old
    return old


# ---------------------------------------------------------------------------
# _upsert_departures
# ---------------------------------------------------------------------------


def test_insert_new_row(db_session, setup):
    scraper, _, route, port = setup
    created, updated = scraper._upsert_departures([_rec(route, port)])
    db_session.commit()

    assert (created, updated) == (1, 0)
    rows = _rows(db_session)
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "operating"
    assert row.ship_name == "フェリーあけぼの"
    assert len(row.content_hash) == 64
    assert row.scraped_at == row.checked_at


def test_same_hash_only_advances_checked_at(db_session, setup):
    scraper, _, route, port = setup
    rec = _rec(route, port)
    scraper._upsert_departures([rec])
    db_session.commit()
    row = _rows(db_session)[0]
    old = _age(row)
    db_session.commit()

    created, updated = scraper._upsert_departures([rec])
    db_session.commit()

    assert (created, updated) == (0, 0)
    assert row.checked_at > old
    assert row.scraped_at == old


def test_changed_hash_advances_both(db_session, setup):
    scraper, _, route, port = setup
    rec = _rec(route, port)
    scraper._upsert_departures([rec])
    db_session.commit()
    row = _rows(db_session)[0]
    old = _age(row)
    db_session.commit()

    rec2 = dict(rec, status=OperationStatusEnum.delayed, status_detail="条件付寄港")
    created, updated = scraper._upsert_departures([rec2])
    db_session.commit()

    assert (created, updated) == (0, 1)
    assert row.status == "delayed"
    assert row.status_detail == "条件付寄港"
    assert row.checked_at > old
    assert row.scraped_at > old


def test_status_none_is_stored_as_null(db_session, setup):
    scraper, _, route, port = setup
    scraper._upsert_departures([_rec(route, port, status=None)])
    db_session.commit()
    assert _rows(db_session)[0].status is None


def test_freeze_keeps_departed_row_untouched(db_session, setup):
    """出港済みの行は status も checked_at も scraped_at も content_hash も変わらない（FR-014・020）。"""
    scraper, _, route, port = setup
    past = datetime.now() - timedelta(hours=1)
    rec = _rec(route, port, scheduled_departure_at=past, freeze_after_departure=True)
    # 出港前に記録された行を用意する
    db_session.add(
        DepartureStatus(
            route_id=route.id,
            port_id=port.id,
            departure_date=rec["departure_date"],
            ship_name=rec["ship_name"],
            status="operating",
            scheduled_departure_at=past,
            content_hash=scraper._departure_hash(rec),
            scraped_at=past - timedelta(hours=3),
            checked_at=past - timedelta(minutes=10),
        )
    )
    db_session.commit()
    row = _rows(db_session)[0]
    before = (row.status, row.checked_at, row.scraped_at, row.content_hash)

    # 出港後に船ステータスが欠航に変わった（次の便の情報）
    scraper._upsert_departures([dict(rec, status=OperationStatusEnum.cancelled)])
    # 同じ内容でも checked_at は進めない
    scraper._upsert_departures([rec])
    db_session.commit()

    assert (row.status, row.checked_at, row.scraped_at, row.content_hash) == before


def test_freeze_uses_new_departure_time_when_delayed(db_session, setup):
    """18:00 発で記録した便が 21:00 発に遅れた → 18:00 を過ぎても、まだ港にいるので更新する。"""
    scraper, _, route, port = setup
    old_dep = datetime.now() - timedelta(minutes=30)
    new_dep = datetime.now() + timedelta(hours=2)
    rec = _rec(route, port, scheduled_departure_at=old_dep, freeze_after_departure=True)
    db_session.add(
        DepartureStatus(
            route_id=route.id,
            port_id=port.id,
            departure_date=rec["departure_date"],
            ship_name=rec["ship_name"],
            status="operating",
            scheduled_departure_at=old_dep,
            content_hash=scraper._departure_hash(rec),
            scraped_at=old_dep - timedelta(hours=1),
            checked_at=old_dep - timedelta(hours=1),
        )
    )
    db_session.commit()

    _, updated = scraper._upsert_departures(
        [
            dict(
                rec,
                scheduled_departure_at=new_dep,
                status=OperationStatusEnum.delayed,
                status_detail="遅延",
            )
        ]
    )
    db_session.commit()

    row = _rows(db_session)[0]
    assert updated == 1
    assert row.status == "delayed"
    assert row.scheduled_departure_at == new_dep


def test_freeze_does_not_insert_departed_row(db_session, setup):
    """既存行が無い出港済みのレコードは INSERT しない（デプロイ直後の初回実行など）。"""
    scraper, _, route, port = setup
    past = datetime.now() - timedelta(minutes=5)
    created, _ = scraper._upsert_departures(
        [_rec(route, port, scheduled_departure_at=past, freeze_after_departure=True)]
    )
    db_session.commit()
    assert created == 0
    assert _rows(db_session) == []


def test_without_freeze_departed_row_is_updated(db_session, setup):
    """freeze しない会社（マリックス）は出港後も更新する。"""
    scraper, _, route, port = setup
    past = datetime.now() - timedelta(hours=1)
    rec = _rec(route, port, scheduled_departure_at=past)
    scraper._upsert_departures([rec])
    scraper._upsert_departures([dict(rec, status=OperationStatusEnum.cancelled)])
    db_session.commit()
    assert _rows(db_session)[0].status == "cancelled"


def test_replace_scope_deletes_old_ship_rows(db_session, setup):
    scraper, _, route, port = setup
    scope = (route.id, port.id, date.today())
    scraper._upsert_departures(
        [
            _rec(
                route,
                port,
                ship_name="",
                status=OperationStatusEnum.no_service,
                scheduled_departure_at=None,
                scheduled_arrival_at=None,
                replace_scope=scope,
            )
        ]
    )
    db_session.commit()

    # 「※下記参照」から船名に変わった
    scraper._upsert_departures([_rec(route, port, replace_scope=scope)])
    db_session.commit()

    rows = _rows(db_session)
    assert [r.ship_name for r in rows] == ["フェリーあけぼの"]


def test_replace_scope_keeps_departed_rows(db_session, setup):
    """出港後の検索で便が返らなくなっても、出港済みの行は消えない（FR-020）。"""
    scraper, _, route, port = setup
    scope = (route.id, port.id, date.today())
    past = datetime.now() - timedelta(hours=1)
    db_session.add(
        DepartureStatus(
            route_id=route.id,
            port_id=port.id,
            departure_date=date.today(),
            ship_name="フェリーあけぼの",
            status="operating",
            scheduled_departure_at=past,
            content_hash="x" * 64,
            scraped_at=past,
            checked_at=past,
        )
    )
    db_session.commit()

    scraper._upsert_departures(
        [
            _rec(
                route,
                port,
                ship_name="",
                status=OperationStatusEnum.no_service,
                scheduled_departure_at=None,
                scheduled_arrival_at=None,
                freeze_after_departure=True,
                replace_scope=scope,
            )
        ]
    )
    db_session.commit()

    names = sorted(r.ship_name for r in _rows(db_session))
    assert names == ["", "フェリーあけぼの"]


def test_replace_scope_does_not_touch_other_keys(db_session, setup):
    scraper, _, route, port = setup
    tomorrow = date.today() + timedelta(days=1)
    scraper._upsert_departures(
        [_rec(route, port, departure_date=tomorrow, ship_name="フェリー波之上")]
    )
    db_session.commit()

    scope = (route.id, port.id, date.today())
    scraper._upsert_departures([_rec(route, port, replace_scope=scope)])
    db_session.commit()

    assert len(_rows(db_session)) == 2


def test_replace_source_deletes_rows_on_other_dates(db_session, setup):
    """同じ便（source_url）の行で、今回書かなかった日付の行は消える。他の便の行は残る。"""
    scraper, _, route, port = setup
    url = "https://example.com/service/downstream20260930/"
    tomorrow = date.today() + timedelta(days=1)
    scraper._upsert_departures(
        [
            _rec(route, port, ship_name="", scheduled_departure_at=None, source_url=url),
            _rec(route, port, departure_date=tomorrow, source_url="https://example.com/other/"),
        ]
    )
    db_session.commit()

    # 遅延で出港日が翌日にずれた
    scraper._upsert_departures(
        [
            _rec(
                route,
                port,
                departure_date=tomorrow,
                ship_name="フェリー波之上",
                scheduled_departure_at=datetime.now() + timedelta(days=1),
                source_url=url,
                replace_source=(route.id, port.id, url),
            )
        ]
    )
    db_session.commit()

    rows = sorted((r.departure_date, r.ship_name, r.source_url) for r in _rows(db_session))
    assert rows == [
        (tomorrow, "フェリーあけぼの", "https://example.com/other/"),
        (tomorrow, "フェリー波之上", url),
    ]


def test_replace_source_keeps_departed_rows(db_session, setup):
    scraper, _, route, port = setup
    url = "https://example.com/service/downstream20260930/"
    past = datetime.now() - timedelta(hours=1)
    db_session.add(
        DepartureStatus(
            route_id=route.id,
            port_id=port.id,
            departure_date=date.today(),
            ship_name="フェリーあけぼの",
            status="operating",
            scheduled_departure_at=past,
            source_url=url,
            content_hash="x" * 64,
            scraped_at=past,
            checked_at=past,
        )
    )
    db_session.commit()

    tomorrow = date.today() + timedelta(days=1)
    scraper._upsert_departures(
        [
            _rec(
                route,
                port,
                departure_date=tomorrow,
                source_url=url,
                replace_source=(route.id, port.id, url),
            )
        ]
    )
    db_session.commit()

    assert len(_rows(db_session)) == 2


# ---------------------------------------------------------------------------
# run()（ルール7：トランザクション）
# ---------------------------------------------------------------------------


def _route_rec(route, **kw):
    rec = {
        "route_id": route.id,
        "status": OperationStatusEnum.operating,
        "valid_date": date.today(),
        "scraped_at": datetime.now(),
    }
    rec.update(kw)
    return rec


def _last_log(db_session):
    return (
        db_session.execute(select(ScraperLog).order_by(ScraperLog.id.desc()))
        .scalars()
        .first()
    )


def test_run_saves_route_and_departures(db_session, setup):
    scraper, _, route, port = setup
    scraper.route_records = [_route_rec(route)]
    scraper.departure_records = [_rec(route, port)]
    scraper.run()
    db_session.commit()

    assert len(db_session.execute(select(OperationStatus)).scalars().all()) == 1
    assert len(_rows(db_session)) == 1
    log = _last_log(db_session)
    assert log.status == ScraperStatusEnum.success
    assert log.error_message is None


def test_run_parse_departures_exception_keeps_route_level(db_session, setup):
    scraper, _, route, port = setup
    scraper.route_records = [_route_rec(route)]
    scraper.departure_records = RuntimeError("detail page broken")
    scraper.run()
    db_session.commit()

    assert len(db_session.execute(select(OperationStatus)).scalars().all()) == 1
    log = _last_log(db_session)
    assert log.status == ScraperStatusEnum.success
    assert log.error_message == "departures: detail page broken"


def test_run_departures_db_error_keeps_route_level(db_session, setup):
    """港別の upsert で DB エラー（一意制約違反）が起きても、航路単位とログはコミットされる。"""
    scraper, _, route, port = setup
    # 2行入れたあとで片方の ship_name をもう片方と同じにして、flush で衝突させる
    scraper.route_records = [_route_rec(route)]
    scraper.departure_records = [
        _rec(route, port, ship_name="A"),
        _rec(route, port, ship_name="B"),
    ]

    original = scraper._upsert_departures

    def _upsert_then_collide(records):
        result = original(records)
        db_session.flush()
        a, b = sorted(_rows(db_session), key=lambda r: r.ship_name)
        b.ship_name = a.ship_name  # flush 時に uniq_departure 違反
        return result

    scraper._upsert_departures = _upsert_then_collide
    scraper.run()
    db_session.commit()

    assert len(db_session.execute(select(OperationStatus)).scalars().all()) == 1
    assert _rows(db_session) == []  # SAVEPOINT ごと戻っている
    log = _last_log(db_session)
    assert log.status == ScraperStatusEnum.success
    assert log.error_message.startswith("departures: ")


def test_run_route_level_flush_error_is_failed(db_session, setup):
    """航路単位の flush で起きたエラーは港別のエラーではなく、今までどおり failed になる。"""
    scraper, _, route, port = setup
    scraper.route_records = [_route_rec(route, valid_date=None)]  # NOT NULL 違反
    scraper.departure_records = [_rec(route, port)]
    scraper.run()
    db_session.commit()

    log = _last_log(db_session)
    assert log.status == ScraperStatusEnum.failed
    assert not log.error_message.startswith("departures:")
    assert db_session.execute(select(OperationStatus)).scalars().all() == []
    assert _rows(db_session) == []


# ---------------------------------------------------------------------------
# JST（US5、FR-016）
# ---------------------------------------------------------------------------


def test_departure_date_and_checked_at_are_same_day_just_after_midnight(
    db_session, setup
):
    """0:30（JST）に実行しても、departure_date と checked_at は同じ暦日で記録される。"""
    from unittest.mock import patch

    scraper, _, route, port = setup
    fixed = datetime(2026, 10, 2, 0, 30)

    class _DateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    with patch("scraper.scrapers.base.datetime", _DateTime):
        scraper._upsert_departures(
            [
                _rec(
                    route,
                    port,
                    departure_date=fixed.date(),
                    scheduled_departure_at=datetime(2026, 10, 2, 5, 50),
                )
            ]
        )
    db_session.commit()

    row = _rows(db_session)[0]
    assert row.checked_at == fixed
    assert row.checked_at.date() == row.departure_date
