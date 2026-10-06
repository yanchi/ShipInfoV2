import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship

# BigInteger that falls back to Integer on SQLite (which requires INTEGER for autoincrement)
_BigIntegerSQLite = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    pass


class OperationStatusEnum(str, enum.Enum):
    # skipped は港の行（departure_statuses）だけで使う。operation_statuses の ENUM には無い
    operating = "operating"
    cancelled = "cancelled"
    delayed = "delayed"
    skipped = "skipped"
    suspended = "suspended"
    unknown = "unknown"
    no_service = "no_service"


class ScraperStatusEnum(str, enum.Enum):
    running = "running"
    success = "success"
    failed = "failed"


class FerryCompany(Base):
    __tablename__ = "ferry_companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    website_url = Column(String(512), nullable=True)
    scraper_class = Column(String(255), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    routes = relationship("Route", back_populates="ferry_company")
    scraper_logs = relationship("ScraperLog", back_populates="ferry_company")


class Route(Base):
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ferry_company_id = Column(Integer, ForeignKey("ferry_companies.id"), nullable=False)
    name = Column(String(255), nullable=False)
    origin_port = Column(String(255), nullable=False)
    destination_port = Column(String(255), nullable=False)
    # "down"（那覇行き）/ "up"（鹿児島行き）。NULL の航路は港別の対象外
    direction = Column(String(8), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    ferry_company = relationship("FerryCompany", back_populates="routes")
    operation_statuses = relationship("OperationStatus", back_populates="route")
    stops = relationship(
        "RouteStop", back_populates="route", order_by="RouteStop.stop_order"
    )


class OperationStatus(Base):
    __tablename__ = "operation_statuses"
    __table_args__ = (
        Index("idx_route_date", "route_id", "valid_date", unique=True),
        Index("idx_date_status", "valid_date", "status"),
    )

    id = Column(_BigIntegerSQLite, primary_key=True, autoincrement=True)
    route_id = Column(Integer, ForeignKey("routes.id"), nullable=False)
    status = Column(
        Enum(OperationStatusEnum), nullable=False, default=OperationStatusEnum.unknown
    )
    status_detail = Column(Text, nullable=True)
    departure_time = Column(DateTime, nullable=True)
    arrival_time = Column(DateTime, nullable=True)
    valid_date = Column(Date, nullable=False)
    scraped_at = Column(DateTime, nullable=False, default=datetime.now)
    source_url = Column(String(512), nullable=True)
    raw_html_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    route = relationship("Route", back_populates="operation_statuses")


class ScraperLog(Base):
    __tablename__ = "scraper_logs"

    id = Column(_BigIntegerSQLite, primary_key=True, autoincrement=True)
    ferry_company_id = Column(Integer, ForeignKey("ferry_companies.id"), nullable=False)
    started_at = Column(DateTime, nullable=False, default=datetime.now)
    finished_at = Column(DateTime, nullable=True)
    status = Column(
        Enum(ScraperStatusEnum), nullable=False, default=ScraperStatusEnum.running
    )
    records_created = Column(Integer, nullable=False, default=0)
    records_updated = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    ferry_company = relationship("FerryCompany", back_populates="scraper_logs")


class Port(Base):
    """航路上の港のマスタ。aliases は表記揺れ（例：["名瀬港", "名瀬"]）。"""

    __tablename__ = "ports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, unique=True)
    aliases = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )


class PortCompanyCode(Base):
    """会社ごとの港の外部コード（マルエーの便検索の港コードなど）。"""

    __tablename__ = "port_company_codes"
    __table_args__ = (
        UniqueConstraint("port_id", "ferry_company_id", name="uniq_port_company"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    port_id = Column(Integer, ForeignKey("ports.id"), nullable=False)
    ferry_company_id = Column(Integer, ForeignKey("ferry_companies.id"), nullable=False)
    external_code = Column(String(32), nullable=False)

    port = relationship("Port")


class RouteStop(Base):
    """航路ごとの寄港順。stop_order = 1 が始発港、最大値が終点。"""

    __tablename__ = "route_stops"
    __table_args__ = (
        UniqueConstraint("route_id", "port_id", name="uniq_route_port"),
        UniqueConstraint("route_id", "stop_order", name="uniq_route_stop_order"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    route_id = Column(Integer, ForeignKey("routes.id"), nullable=False)
    port_id = Column(Integer, ForeignKey("ports.id"), nullable=False)
    stop_order = Column(SmallInteger, nullable=False)
    day_offset = Column(SmallInteger, nullable=False, default=0)

    route = relationship("Route", back_populates="stops")
    port = relationship("Port")


class DepartureStatus(Base):
    """会社 × 方向 × 出発港 × 出港日 × 船 の港別ステータス。

    status が None = 運航予定（未発表）。
    status が no_service で operated_by_company_id がある = 他社が運航。
    """

    __tablename__ = "departure_statuses"
    __table_args__ = (
        UniqueConstraint(
            "route_id", "port_id", "departure_date", "ship_name", name="uniq_departure"
        ),
        Index("idx_departure_date_port", "departure_date", "port_id"),
    )

    id = Column(_BigIntegerSQLite, primary_key=True, autoincrement=True)
    route_id = Column(Integer, ForeignKey("routes.id"), nullable=False)
    port_id = Column(Integer, ForeignKey("ports.id"), nullable=False)
    departure_date = Column(Date, nullable=False)
    ship_name = Column(String(255), nullable=False, default="")
    # Enum 型にすると MySQL 側の VARCHAR(32) とずれるので文字列で持つ（値は OperationStatusEnum）
    status = Column(String(32), nullable=True)
    status_detail = Column(Text, nullable=True)
    scheduled_departure_at = Column(DateTime, nullable=True)
    scheduled_arrival_at = Column(DateTime, nullable=True)
    operated_by_company_id = Column(
        Integer, ForeignKey("ferry_companies.id"), nullable=True
    )
    source_url = Column(String(512), nullable=True)
    content_hash = Column(String(64), nullable=False)
    scraped_at = Column(DateTime, nullable=False, default=datetime.now)
    checked_at = Column(DateTime, nullable=False, default=datetime.now)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )
