from sqlalchemy import select

from scraper.db.models import FerryCompany
from scraper.scrapers.base import BaseScraper
from scraper.scrapers.marix_line import MarixLine
from scraper.scrapers.marue_ferry import MarueFerry

# DB の ferry_companies.scraper_class カラム値 → Pythonクラス のマッピング
SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "MarueFerry": MarueFerry,
    "MarixLine": MarixLine,
}


def get_all_scrapers(session) -> list[tuple[type[BaseScraper], int]]:
    """Return list of (ScraperClass, company_id) for all active companies."""
    companies = session.execute(
        select(FerryCompany).where(FerryCompany.active.is_(True))
    ).scalars().all()
    result = []
    for company in companies:
        scraper_cls = SCRAPER_REGISTRY.get(company.scraper_class or "")
        if scraper_cls:
            result.append((scraper_cls, company.id))
    return result
