import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scraper.db.models import Base, FerryCompany, Route


@pytest.fixture
def db_session():
    """In-memory SQLite session for unit tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def marue_ferry_company(db_session):
    """マルエーフェリー会社 + 上り/下り航路をDBに登録。"""
    company = FerryCompany(
        name="マルエーフェリー",
        scraper_class="MarueFerry",
        active=True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db_session.add(company)
    db_session.flush()

    down = Route(
        ferry_company_id=company.id,
        name="鹿児島〜那覇（下り）",
        origin_port="鹿児島",
        destination_port="那覇",
        active=True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    up = Route(
        ferry_company_id=company.id,
        name="那覇〜鹿児島（上り）",
        origin_port="那覇",
        destination_port="鹿児島",
        active=True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db_session.add_all([down, up])
    db_session.commit()
    return company


@pytest.fixture
def marix_line_company(db_session):
    """マリックスライン会社 + 上り/下り航路をDBに登録。"""
    company = FerryCompany(
        name="マリックスライン",
        scraper_class="MarixLine",
        active=True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db_session.add(company)
    db_session.flush()

    down = Route(
        ferry_company_id=company.id,
        name="鹿児島〜那覇（下り）",
        origin_port="鹿児島",
        destination_port="那覇",
        active=True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    up = Route(
        ferry_company_id=company.id,
        name="那覇〜鹿児島（上り）",
        origin_port="那覇",
        destination_port="鹿児島",
        active=True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db_session.add_all([down, up])
    db_session.commit()
    return company
