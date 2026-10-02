"""SQLAlchemy モデルの列が、実際の DB（Symfony のマイグレーションで作ったもの）にあるかを確かめる。

DB のスキーマは Symfony 側のマイグレーションが正で、スクレイパーのテストは SQLite にモデルから
テーブルを作るため、モデルにだけある列に気づけない（scraper_logs.created_at で本番相当の DB が
落ちていた）。CI ではマイグレーション後の MySQL に対してこれを走らせる。

    python -m scraper.db.check_schema
"""

import sys

from sqlalchemy import MetaData, inspect
from sqlalchemy.engine import Engine


def find_missing_columns(metadata: MetaData, engine: Engine) -> dict[str, list[str]]:
    """モデルにあって DB に無い列（テーブルごと無いときは ["*"]）。DB にだけある列は問題にしない。"""
    insp = inspect(engine)
    missing: dict[str, list[str]] = {}
    for table in metadata.sorted_tables:
        if not insp.has_table(table.name):
            missing[table.name] = ["*"]
            continue
        db_columns = {c["name"] for c in insp.get_columns(table.name)}
        model_only = sorted(c.name for c in table.columns if c.name not in db_columns)
        if model_only:
            missing[table.name] = model_only
    return missing


def main() -> int:
    from scraper.db.connection import engine
    from scraper.db.models import Base

    missing = find_missing_columns(Base.metadata, engine)
    if not missing:
        print(f"OK: all model columns exist in {engine.url.database}")
        return 0

    print(f"NG: model columns missing in {engine.url.database}", file=sys.stderr)
    for table, columns in missing.items():
        print(f"  {table}: {', '.join(columns)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
