import enum
import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime

import structlog
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from scraper.db.models import (
    DepartureStatus,
    OperationStatus,
    ScraperLog,
    ScraperStatusEnum,
)
from scraper.utils.http import create_session

log = structlog.get_logger()


class BaseScraper(ABC):
    """Abstract base class for all ferry company scrapers."""

    company_id: int

    def __init__(
        self, session: Session, company_id: int, *, retry_post: bool = False
    ) -> None:
        self.session = session
        self.company_id = company_id
        self.http = create_session(retry_post=retry_post)
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

    def parse_departures(self) -> list[dict]:
        """
        港別（出発港 × 出港日 × 船）のレコードを返す。fetch() / parse() の後に呼ばれる。
        港別に対応していない会社はデフォルトの [] のまま。

        Each dict must contain:
            - route_id: int
            - port_id: int
            - departure_date: date
            - status: OperationStatusEnum | None（None = 運航予定）
        Optional keys:
            - ship_name: str（便が無い行は ""）
            - status_detail: str
            - scheduled_departure_at / scheduled_arrival_at: datetime
            - operated_by_company_id: int（他社が運航している no_service 行）
            - source_url: str
            - freeze_after_departure: bool（出港済みの行を更新・作成しない）
            - replace_scope: (route_id, port_id, departure_date)（このキーで今回に無い船の行を消す）
            - replace_source: (route_id, port_id, source_url)（同じ便の行のうち、今回書かなかった日付・船の行を消す。
              出港済みの行を残すのは freeze_after_departure の便だけ）
        """
        return []

    def run(self) -> None:
        started_at = datetime.now()
        scraper_log = ScraperLog(
            ferry_company_id=self.company_id,
            started_at=started_at,
            status=ScraperStatusEnum.running,
        )
        self.session.add(scraper_log)
        self.session.flush()

        try:
            html = self.fetch()
            records = self.parse(html)
            created, updated = self._upsert(records, html)
            # 航路単位の DB エラーはここで出す（港別の SAVEPOINT の中で出ると港別のエラー扱いになるため）
            self.session.flush()
        except Exception as exc:
            # flush に失敗した Session はロールバックしないとコミットできないので、
            # 今回の書き込みを捨てて failed のログだけ残す
            self.session.rollback()
            self.session.add(
                ScraperLog(
                    ferry_company_id=self.company_id,
                    started_at=started_at,
                    finished_at=datetime.now(),
                    status=ScraperStatusEnum.failed,
                    error_message=str(exc),
                )
            )
            self._log.error("scraper_error", error=str(exc))
            return

        departures_error = None
        try:
            # 港別の処理は SAVEPOINT の中で行い、失敗してもここだけ戻す
            with self.session.begin_nested():
                departures = self.parse_departures()
                d_created, d_updated = self._upsert_departures(departures)
                self.session.flush()
            self._log.info("departures_done", created=d_created, updated=d_updated)
        except Exception as exc:
            departures_error = f"departures: {exc}"
            self._log.error("departures_error", error=str(exc))

        scraper_log.status = ScraperStatusEnum.success
        scraper_log.finished_at = datetime.now()
        scraper_log.records_created = created
        scraper_log.records_updated = updated
        scraper_log.error_message = departures_error
        self._log.info("scraper_done", created=created, updated=updated)

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

    # ------------------------------------------------------------------
    # 港別（departure_statuses）
    # ------------------------------------------------------------------

    @staticmethod
    def _departure_hash(rec: dict) -> str:
        """status・status_detail・ship_name・各日時・operated_by の SHA-256。"""

        def norm(v):
            if isinstance(v, enum.Enum):
                return v.value
            if hasattr(
                v, "isoformat"
            ):  # date / datetime（テストで差し替えたサブクラスも含む）
                return v.isoformat()
            return v

        payload = [
            norm(rec.get("status")),
            rec.get("status_detail"),
            rec.get("ship_name") or "",
            norm(rec.get("scheduled_departure_at")),
            norm(rec.get("scheduled_arrival_at")),
            rec.get("operated_by_company_id"),
        ]
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False).encode()
        ).hexdigest()

    def _upsert_departures(self, records: list[dict]) -> tuple[int, int]:
        """departure_statuses を更新する（data-model.md の更新ルール1〜5）。

        1. 行が無い → INSERT
        2. content_hash が同じ → checked_at だけ更新
        3. content_hash が違う → 内容と scraped_at・checked_at を更新
        4. freeze_after_departure で出港済み → 既存行は一切更新しない。既存行が無ければ INSERT しない
           （出港済みかは今回の出港予定で判定する。遅延で後ろにずれた便は、まだ更新する）
        5. replace_scope があれば、そのキーで今回に無い ship_name の行を消す（出港済みの行は残す）
        6. replace_source があれば、同じ航路・港・source_url（＝同じ便）で今回書かなかった
           (departure_date, ship_name) の行を消す。遅延で出港日がずれたときに、前の日付の行を
           残さないため。古い行は同じ便の新しい情報で置き換わったものなので、出港予定を
           過ぎていても消す（元の出港時刻の後に遅延が発表されることがある）。
           ただし freeze_after_departure の便は、ルール4に合わせて出港済みの行を残す
        """
        now = datetime.now()
        created = updated = 0
        scopes: dict[tuple, set[str]] = {}
        sources: dict[tuple, set[tuple]] = {}
        frozen_sources: set[tuple] = set()
        processed: set[tuple] = set()

        for rec in records:
            ship_name = rec.get("ship_name") or ""
            key = (rec["route_id"], rec["port_id"], rec["departure_date"], ship_name)
            scope = rec.get("replace_scope")
            if scope is not None:
                scopes.setdefault(tuple(scope), set()).add(ship_name)
            source = rec.get("replace_source")
            if source is not None:
                sources.setdefault(tuple(source), set()).add((key[2], ship_name))
                if rec.get("freeze_after_departure"):
                    frozen_sources.add(tuple(source))
            if key in processed:
                self._log.warning("departure_duplicate_key", key=[str(k) for k in key])
                continue
            processed.add(key)

            status = rec.get("status")
            status_value = status.value if isinstance(status, enum.Enum) else status
            content_hash = self._departure_hash(rec)
            freeze = bool(rec.get("freeze_after_departure"))

            existing = self.session.execute(
                select(DepartureStatus).where(
                    DepartureStatus.route_id == key[0],
                    DepartureStatus.port_id == key[1],
                    DepartureStatus.departure_date == key[2],
                    DepartureStatus.ship_name == key[3],
                )
            ).scalar_one_or_none()

            if existing is not None:
                # 出港したかは、今回取れた出港予定（遅延で後ろにずれていればそちら）で判定する
                departure_at = (
                    rec.get("scheduled_departure_at") or existing.scheduled_departure_at
                )
                if freeze and departure_at is not None and departure_at < now:
                    continue  # 出港済みで確定（checked_at も進めない）
                if existing.content_hash == content_hash:
                    existing.checked_at = now
                    continue
                existing.status = status_value
                existing.status_detail = rec.get("status_detail")
                existing.scheduled_departure_at = rec.get("scheduled_departure_at")
                existing.scheduled_arrival_at = rec.get("scheduled_arrival_at")
                existing.operated_by_company_id = rec.get("operated_by_company_id")
                existing.source_url = rec.get("source_url")
                existing.content_hash = content_hash
                existing.scraped_at = now
                existing.checked_at = now
                updated += 1
            else:
                dep_at = rec.get("scheduled_departure_at")
                if freeze and dep_at is not None and dep_at < now:
                    continue  # 出港後の初回取得は、今の船ステータスを過去の便に当てはめない
                self.session.add(
                    DepartureStatus(
                        route_id=key[0],
                        port_id=key[1],
                        departure_date=key[2],
                        ship_name=ship_name,
                        status=status_value,
                        status_detail=rec.get("status_detail"),
                        scheduled_departure_at=dep_at,
                        scheduled_arrival_at=rec.get("scheduled_arrival_at"),
                        operated_by_company_id=rec.get("operated_by_company_id"),
                        source_url=rec.get("source_url"),
                        content_hash=content_hash,
                        scraped_at=now,
                        checked_at=now,
                    )
                )
                created += 1

        for (route_id, port_id, departure_date), names in scopes.items():
            self.session.execute(
                delete(DepartureStatus)
                .where(
                    DepartureStatus.route_id == route_id,
                    DepartureStatus.port_id == port_id,
                    DepartureStatus.departure_date == departure_date,
                    DepartureStatus.ship_name.not_in(names),
                    or_(
                        DepartureStatus.scheduled_departure_at.is_(None),
                        DepartureStatus.scheduled_departure_at >= now,
                    ),
                )
                .execution_options(synchronize_session="fetch")
            )

        for source, written in sources.items():
            route_id, port_id, source_url = source
            query = select(DepartureStatus).where(
                DepartureStatus.route_id == route_id,
                DepartureStatus.port_id == port_id,
                DepartureStatus.source_url == source_url,
            )
            if source in frozen_sources:
                query = query.where(
                    or_(
                        DepartureStatus.scheduled_departure_at.is_(None),
                        DepartureStatus.scheduled_departure_at >= now,
                    )
                )
            stale = self.session.execute(query).scalars()
            for row in stale:
                if (row.departure_date, row.ship_name) not in written:
                    self.session.delete(row)

        return created, updated
