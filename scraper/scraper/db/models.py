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
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship

# BigInteger that falls back to Integer on SQLite (which requires INTEGER for autoincrement)
_BigIntegerSQLite = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    pass


class OperationStatusEnum(str, enum.Enum):
    operating = "operating"
    cancelled = "cancelled"
    delayed = "delayed"
    suspended = "suspended"
    unknown = "unknown"


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
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    routes = relationship("Route", back_populates="ferry_company")
    scraper_logs = relationship("ScraperLog", back_populates="ferry_company")


class Route(Base):
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ferry_company_id = Column(Integer, ForeignKey("ferry_companies.id"), nullable=False)
    name = Column(String(255), nullable=False)
    origin_port = Column(String(255), nullable=False)
    destination_port = Column(String(255), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    ferry_company = relationship("FerryCompany", back_populates="routes")
    operation_statuses = relationship("OperationStatus", back_populates="route")


class OperationStatus(Base):
    __tablename__ = "operation_statuses"
    __table_args__ = (
        Index("idx_route_date", "route_id", "valid_date", unique=True),
        Index("idx_date_status", "valid_date", "status"),
    )

    id = Column(_BigIntegerSQLite, primary_key=True, autoincrement=True)
    route_id = Column(Integer, ForeignKey("routes.id"), nullable=False)
    status = Column(Enum(OperationStatusEnum), nullable=False, default=OperationStatusEnum.unknown)
    status_detail = Column(Text, nullable=True)
    departure_time = Column(DateTime, nullable=True)
    arrival_time = Column(DateTime, nullable=True)
    valid_date = Column(Date, nullable=False)
    scraped_at = Column(DateTime, nullable=False, default=datetime.now)
    source_url = Column(String(512), nullable=True)
    raw_html_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    route = relationship("Route", back_populates="operation_statuses")


class ScraperLog(Base):
    __tablename__ = "scraper_logs"

    id = Column(_BigIntegerSQLite, primary_key=True, autoincrement=True)
    ferry_company_id = Column(Integer, ForeignKey("ferry_companies.id"), nullable=False)
    started_at = Column(DateTime, nullable=False, default=datetime.now)
    finished_at = Column(DateTime, nullable=True)
    status = Column(Enum(ScraperStatusEnum), nullable=False, default=ScraperStatusEnum.running)
    records_created = Column(Integer, nullable=False, default=0)
    records_updated = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    ferry_company = relationship("FerryCompany", back_populates="scraper_logs")
