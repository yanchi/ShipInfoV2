import logging
import sys
import time

import schedule
import structlog

from scraper.config import settings
from scraper.db.connection import get_session
from scraper.scrapers import get_all_scrapers

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, settings.log_level, logging.INFO)
    ),
)

log = structlog.get_logger()


def run_all() -> None:
    log.info("scrape_cycle_start")

    with get_session() as session:
        scrapers = get_all_scrapers(session)

    if not scrapers:
        log.warning("no_active_scrapers")
        log.info("scrape_cycle_done")
        return

    for ScraperClass, company_id in scrapers:
        with get_session() as session:
            ScraperClass(session, company_id).run()

    log.info("scrape_cycle_done")


def main() -> None:
    once = "--once" in sys.argv

    log.info("scraper_started", interval_minutes=settings.interval_minutes, once=once)
    run_all()

    if once:
        return

    schedule.every(settings.interval_minutes).minutes.do(run_all)
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
