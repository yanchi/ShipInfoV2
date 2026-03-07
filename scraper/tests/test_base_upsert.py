"""
BaseScraper._upsert のDBレベル動作テスト。

- 新規レコード作成
- 同一HTMLハッシュのときはスキップ（変更なし）
- HTMLが変わったときは既存レコードを更新
- created / updated カウントが正確に返る
"""
import hashlib
from datetime import date, datetime

import pytest
from sqlalchemy import select

from scraper.db.models import FerryCompany, OperationStatus, OperationStatusEnum, Route
from scraper.scrapers.base import BaseScraper


# ---------------------------------------------------------------------------
# テスト用の最小限 BaseScraper 実装
# ---------------------------------------------------------------------------

class _StubScraper(BaseScraper):
    """_upsert のみテストするためのスタブ実装。"""

    def fetch(self) -> str:
        return "<html/>"

    def parse(self, html: str) -> list[dict]:
        return []


# ---------------------------------------------------------------------------
# フィクスチャ
# ---------------------------------------------------------------------------

@pytest.fixture
def company_and_route(db_session):
    """テスト用フェリー会社と航路を1件ずつ登録して返す。"""
    company = FerryCompany(
        name="テスト会社",
        scraper_class="_StubScraper",
        active=True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db_session.add(company)
    db_session.flush()

    route = Route(
        ferry_company_id=company.id,
        name="テスト航路",
        origin_port="A港",
        destination_port="B港",
        active=True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db_session.add(route)
    db_session.commit()
    return company, route


@pytest.fixture
def scraper(db_session, company_and_route):
    company, _ = company_and_route
    return _StubScraper(db_session, company.id)


# ---------------------------------------------------------------------------
# テスト
# ---------------------------------------------------------------------------

def test_upsert_creates_new_record(db_session, scraper, company_and_route):
    """存在しない route_id + valid_date に対して新規レコードが作成される。"""
    _, route = company_and_route

    records = [
        {
            "route_id": route.id,
            "status": OperationStatusEnum.operating,
            "valid_date": date(2026, 3, 10),
            "scraped_at": datetime.now(),
            "source_url": "https://example.com",
        }
    ]

    created, updated = scraper._upsert(records, "<html>v1</html>")

    assert created == 1
    assert updated == 0

    row = db_session.execute(
        select(OperationStatus).where(
            OperationStatus.route_id == route.id,
            OperationStatus.valid_date == date(2026, 3, 10),
        )
    ).scalar_one()

    assert row.status == OperationStatusEnum.operating
    assert row.source_url == "https://example.com"
    assert row.raw_html_hash == hashlib.sha256(b"<html>v1</html>").hexdigest()


def test_upsert_skips_when_html_unchanged(db_session, scraper, company_and_route):
    """同一HTMLハッシュのとき既存レコードはスキップされ updated=0 になる。"""
    _, route = company_and_route
    html = "<html>same</html>"

    records = [
        {
            "route_id": route.id,
            "status": OperationStatusEnum.operating,
            "valid_date": date(2026, 3, 11),
            "scraped_at": datetime.now(),
        }
    ]

    # 1回目：新規作成
    scraper._upsert(records, html)
    db_session.commit()

    # 2回目：同じHTML → スキップ
    created, updated = scraper._upsert(records, html)

    assert created == 0
    assert updated == 0


def test_upsert_updates_when_html_changed(db_session, scraper, company_and_route):
    """HTMLが変わったとき既存レコードが更新され updated=1 になる。"""
    _, route = company_and_route

    records_v1 = [
        {
            "route_id": route.id,
            "status": OperationStatusEnum.operating,
            "valid_date": date(2026, 3, 12),
            "scraped_at": datetime.now(),
        }
    ]
    records_v2 = [
        {
            "route_id": route.id,
            "status": OperationStatusEnum.cancelled,
            "valid_date": date(2026, 3, 12),
            "status_detail": "台風のため欠航",
            "scraped_at": datetime.now(),
        }
    ]

    scraper._upsert(records_v1, "<html>v1</html>")
    db_session.commit()

    created, updated = scraper._upsert(records_v2, "<html>v2</html>")

    assert created == 0
    assert updated == 1

    row = db_session.execute(
        select(OperationStatus).where(
            OperationStatus.route_id == route.id,
            OperationStatus.valid_date == date(2026, 3, 12),
        )
    ).scalar_one()

    assert row.status == OperationStatusEnum.cancelled
    assert row.status_detail == "台風のため欠航"
    assert row.raw_html_hash == hashlib.sha256(b"<html>v2</html>").hexdigest()


def test_upsert_counts_mixed_records(db_session, scraper, company_and_route):
    """新規・更新・スキップが混在するとき、カウントが正確に返る。"""
    _, route = company_and_route

    # 事前に 3/13 を作成（同じHTML）
    pre_records = [
        {
            "route_id": route.id,
            "status": OperationStatusEnum.operating,
            "valid_date": date(2026, 3, 13),
            "scraped_at": datetime.now(),
        }
    ]
    scraper._upsert(pre_records, "<html>old</html>")
    db_session.commit()

    # 3/13: 別HTML → update、3/14: 新規 → create
    new_records = [
        {
            "route_id": route.id,
            "status": OperationStatusEnum.delayed,
            "valid_date": date(2026, 3, 13),
            "scraped_at": datetime.now(),
        },
        {
            "route_id": route.id,
            "status": OperationStatusEnum.operating,
            "valid_date": date(2026, 3, 14),
            "scraped_at": datetime.now(),
        },
    ]

    created, updated = scraper._upsert(new_records, "<html>new</html>")

    assert created == 1
    assert updated == 1
