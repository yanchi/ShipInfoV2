"""
CompanyA scraper - example implementation.

Replace the URL, parsing logic, and route_id mapping to match
the actual target ferry company website.
"""
from datetime import date, datetime

from bs4 import BeautifulSoup

from scraper.db.models import OperationStatusEnum
from scraper.scrapers.base import BaseScraper

SOURCE_URL = "https://example.com/operation-status"

# Map route name (as it appears on the website) to route.id in the DB
ROUTE_NAME_TO_ID: dict[str, int] = {
    "函館-青森": 1,
}


class CompanyAScraper(BaseScraper):
    def fetch(self) -> str:
        response = self.http.get(SOURCE_URL)
        response.raise_for_status()
        return response.text

    def parse(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        records = []

        # Example: find a table with class "operation-table"
        table = soup.find("table", class_="operation-table")
        if not table:
            self._log.warning("table_not_found", url=SOURCE_URL)
            return records

        for row in table.find_all("tr")[1:]:  # skip header row
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            route_name = cells[0].get_text(strip=True)
            date_str = cells[1].get_text(strip=True)
            status_str = cells[2].get_text(strip=True)

            route_id = ROUTE_NAME_TO_ID.get(route_name)
            if route_id is None:
                self._log.warning("unknown_route", route=route_name)
                continue

            try:
                valid_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                self._log.warning("invalid_date", date_str=date_str)
                continue

            status = self._parse_status(status_str)

            records.append({
                "route_id": route_id,
                "status": status,
                "status_detail": status_str if status != OperationStatusEnum.operating else None,
                "valid_date": valid_date,
                "scraped_at": datetime.now(),
                "source_url": SOURCE_URL,
            })

        return records

    def _parse_status(self, text: str) -> OperationStatusEnum:
        if "欠航" in text:
            return OperationStatusEnum.cancelled
        if "遅延" in text or "遅れ" in text:
            return OperationStatusEnum.delayed
        if "運休" in text:
            return OperationStatusEnum.suspended
        if "運航" in text or "通常" in text:
            return OperationStatusEnum.operating
        return OperationStatusEnum.unknown
