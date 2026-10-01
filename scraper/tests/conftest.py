import pytest
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from scraper.db.models import Base, FerryCompany, Port, PortCompanyCode, Route, RouteStop

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# マイグレーション Version20261001000000 と同じ港・寄港順
PORTS = [
    ("鹿児島", ["鹿児島新港", "鹿児島"], "50"),
    ("名瀬", ["名瀬港", "名瀬"], "70"),
    ("亀徳", ["亀徳新港", "亀徳港", "亀徳"], "78"),
    ("和泊", ["和泊港", "和泊"], "80"),
    ("与論", ["与論港", "与論"], "82"),
    ("本部", ["本部港", "本部"], "84"),
    ("那覇", ["那覇港", "那覇"], "83"),
]
STOPS = {
    "down": [("鹿児島", 0), ("名瀬", 1), ("亀徳", 1), ("和泊", 1), ("与論", 1), ("本部", 1), ("那覇", 1)],
    "up": [("那覇", 0), ("本部", 0), ("与論", 0), ("和泊", 0), ("亀徳", 0), ("名瀬", 0), ("鹿児島", 1)],
}


def read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def setup_port_master(session, *companies) -> dict[str, Port]:
    """港・寄港順・direction を入れる（マルエーの会社には港コードも）。港名 → Port を返す。"""
    ports = {p.name: p for p in session.query(Port).all()}
    if not ports:
        for name, aliases, _ in PORTS:
            ports[name] = Port(name=name, aliases=aliases)
            session.add(ports[name])
        session.flush()
    for company in companies:
        for route in session.query(Route).filter(Route.ferry_company_id == company.id):
            route.direction = "down" if route.origin_port == "鹿児島" else "up"
            for i, (name, offset) in enumerate(STOPS[route.direction], start=1):
                session.add(RouteStop(route_id=route.id, port_id=ports[name].id, stop_order=i, day_offset=offset))
        if company.scraper_class == "MarueFerry":
            for name, _, code in PORTS:
                session.add(PortCompanyCode(port_id=ports[name].id, ferry_company_id=company.id, external_code=code))
    session.commit()
    return ports


@pytest.fixture
def db_session():
    """In-memory SQLite session for unit tests."""
    engine = create_engine("sqlite:///:memory:")

    # pysqlite は BEGIN を自前で出すため SAVEPOINT（session.begin_nested）が正しく効かない。
    # SQLAlchemy ドキュメントのレシピで、BEGIN を SQLAlchemy 側から出すようにする。
    @event.listens_for(engine, "connect")
    def _do_connect(dbapi_connection, connection_record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _do_begin(conn):
        conn.exec_driver_sql("BEGIN")

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
