from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine

from scraper.db.check_schema import find_missing_columns


def _model() -> MetaData:
    metadata = MetaData()
    Table(
        "logs",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("created_at", String),
    )
    Table("ports", metadata, Column("id", Integer, primary_key=True))
    return metadata


def test_reports_columns_and_tables_missing_in_db():
    engine = create_engine("sqlite:///:memory:")
    db = MetaData()
    Table("logs", db, Column("id", Integer, primary_key=True))
    db.create_all(engine)

    assert find_missing_columns(_model(), engine) == {
        "logs": ["created_at"],
        "ports": ["*"],
    }


def test_ignores_columns_only_in_db():
    engine = create_engine("sqlite:///:memory:")
    db = MetaData()
    Table(
        "logs",
        db,
        Column("id", Integer, primary_key=True),
        Column("created_at", String),
        Column("symfony_only", String),
    )
    Table("ports", db, Column("id", Integer, primary_key=True))
    db.create_all(engine)

    assert find_missing_columns(_model(), engine) == {}
