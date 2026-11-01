"""pytest プラグイン：テストごとに、終わったときの DB の行を JSON Lines に書き出す（17-scraper-refactor の FR-001）。

整理の前と後で同じテストを流し、出力を diff して「DB に書く内容が変わらない」ことを確かめる。
使い方は quickstart.md。リポジトリのテストには入れない（テストの数を変えないため）。

    PYTHONHASHSEED=0 SNAPSHOT_OUT=/tmp/before.jsonl python -m pytest tests/ -q -p snapshot_plugin

実行のたびに変わる時刻の列（作成・更新・取得・確認・開始・終了）と id は書かない。
行は中身で並べ替える（挿入順に依存しない）。
"""

import json
import os

import pytest
from sqlalchemy import text

from scraper.db.models import Base

# 実行時刻で決まる列（テストが固定していないものを含む）と、挿入順で決まる代理キー
_VOLATILE = {
    "id",
    "created_at",
    "updated_at",
    "scraped_at",
    "checked_at",
    "started_at",
    "finished_at",
}


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_teardown(item, nextitem):
    """フィクスチャの後片付け（db_session の drop_all）より先に読む。"""
    out = os.environ.get("SNAPSHOT_OUT")
    session = getattr(item, "funcargs", {}).get("db_session")
    if not out or session is None:
        return
    # 直接 _upsert_departures() を呼ぶテストはコミットしないので、ロールバックせずにそのまま読む
    tables: dict[str, list[dict] | str] = {}
    # 別の接続を開かない（:memory: の SQLite は接続が1つ）
    for name in sorted(Base.metadata.tables):
        try:
            rows = session.execute(text(f"SELECT * FROM {name}")).mappings().all()
        except Exception as e:  # 例外を期待するテストでセッションが壊れているとき
            session.rollback()
            tables[name] = f"error: {type(e).__name__}"
            continue
        tables[name] = sorted(
            ({k: str(v) for k, v in row.items() if k not in _VOLATILE} for row in rows),
            key=lambda r: json.dumps(r, sort_keys=True, ensure_ascii=False),
        )
    with open(out, "a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {"test": item.nodeid, "tables": tables},
                sort_keys=True,
                ensure_ascii=False,
            )
            + "\n"
        )
