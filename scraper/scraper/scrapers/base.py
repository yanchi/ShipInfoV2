import hashlib
from abc import ABC, abstractmethod
from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from scraper.db.models import OperationStatus, ScraperLog, ScraperStatusEnum
from scraper.utils.http import create_session

log = structlog.get_logger()


class BaseScraper(ABC):
    """Abstract base class for all ferry company scrapers."""

    company_id: int

    def __init__(self, session: Session, company_id: int) -> None:
        self.session = session
        self.company_id = company_id
        self.http = create_session()
        self._log = log.bind(scraper=self.__class__.__name__, company_id=company_id)

    @abstractmethod
    def fetch(self) -> str:
        """Fetch raw HTML from the ferry company website."""
        ...

    @abstractmethod
    def parse(self, html: str) -> list[dict]:
        """
        Parse HTML into a list of operation status dicts.

        Each dict must contain:
            - route_id: int
            - status: OperationStatusEnum
            - valid_date: date
            - scraped_at: datetime
        Optional keys:
            - status_detail: str
            - departure_time: datetime
            - arrival_time: datetime
            - source_url: str
        """
        ...

    def run(self) -> None:
        scraper_log = ScraperLog(
            ferry_company_id=self.company_id,
            started_at=datetime.now(),
            status=ScraperStatusEnum.running,
        )
        self.session.add(scraper_log)
        self.session.flush()

        try:
            html = self.fetch()
            records = self.parse(html)
            created, updated = self._upsert(records, html)

            scraper_log.status = ScraperStatusEnum.success
            scraper_log.finished_at = datetime.now()
            scraper_log.records_created = created
            scraper_log.records_updated = updated
            self._log.info("scraper_done", created=created, updated=updated)

        except Exception as exc:
            scraper_log.status = ScraperStatusEnum.failed
            scraper_log.finished_at = datetime.now()
            scraper_log.error_message = str(exc)
            self._log.error("scraper_error", error=str(exc))

    def _upsert(self, records: list[dict], html: str) -> tuple[int, int]:
        """Insert or update operation_statuses; skip if raw HTML unchanged."""
        created = updated = 0
        html_hash = hashlib.sha256(html.encode()).hexdigest()

        for rec in records:
            existing = self.session.execute(
                select(OperationStatus).where(
                    OperationStatus.route_id == rec["route_id"],
                    OperationStatus.valid_date == rec["valid_date"],
                )
            ).scalar_one_or_none()

            if existing:
                if existing.raw_html_hash == html_hash:
                    continue  # No change
                existing.status = rec["status"]
                existing.status_detail = rec.get("status_detail")
                existing.departure_time = rec.get("departure_time")
                existing.arrival_time = rec.get("arrival_time")
                existing.scraped_at = rec.get("scraped_at", datetime.now())
                existing.source_url = rec.get("source_url")
                existing.raw_html_hash = html_hash
                updated += 1
            else:
                status = OperationStatus(
                    route_id=rec["route_id"],
                    status=rec["status"],
                    status_detail=rec.get("status_detail"),
                    departure_time=rec.get("departure_time"),
                    arrival_time=rec.get("arrival_time"),
                    valid_date=rec["valid_date"],
                    scraped_at=rec.get("scraped_at", datetime.now()),
                    source_url=rec.get("source_url"),
                    raw_html_hash=html_hash,
                )
                self.session.add(status)
                created += 1

        return created, updated
