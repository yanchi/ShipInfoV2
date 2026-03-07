import responses as resp_mock
import pytest

from scraper.scrapers.company_a import CompanyAScraper, SOURCE_URL
from scraper.db.models import FerryCompany, Route, OperationStatusEnum


SAMPLE_HTML = """
<html><body>
<table class="operation-table">
  <tr><th>航路</th><th>日付</th><th>状況</th></tr>
  <tr><td>函館-青森</td><td>2026-03-07</td><td>欠航（強風のため）</td></tr>
</table>
</body></html>
"""


@pytest.fixture
def seed_db(db_session):
    company = FerryCompany(name="テストフェリー", scraper_class="CompanyAScraper")
    db_session.add(company)
    db_session.flush()

    route = Route(ferry_company_id=company.id, name="函館-青森")
    route.id = 1
    db_session.add(route)
    db_session.commit()
    return company


@resp_mock.activate
def test_parse_cancelled(db_session, seed_db):
    resp_mock.add(resp_mock.GET, SOURCE_URL, body=SAMPLE_HTML, status=200)

    scraper = CompanyAScraper(db_session, seed_db.id)
    html = scraper.fetch()
    records = scraper.parse(html)

    assert len(records) == 1
    assert records[0]["status"] == OperationStatusEnum.cancelled
    assert records[0]["status_detail"] == "欠航（強風のため）"
