from scraper.db.models import FerryCompany
from scraper.scrapers.base import BaseScraper
from scraper.scrapers.company_a import CompanyAScraper

# Map scraper_class column value to Python class
SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "CompanyAScraper": CompanyAScraper,
}


def get_all_scrapers(session) -> list[tuple[type[BaseScraper], int]]:
    """Return list of (ScraperClass, company_id) for all active companies."""
    companies = (
        session.query(FerryCompany)
        .filter(FerryCompany.active.is_(True))
        .all()
    )
    result = []
    for company in companies:
        scraper_cls = SCRAPER_REGISTRY.get(company.scraper_class or "")
        if scraper_cls:
            result.append((scraper_cls, company.id))
    return result
