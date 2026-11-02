"""pytest プラグイン：テストごとに、スクレイパーが返したものと DB の行を JSON Lines に書き出す（17-scraper-refactor の FR-001）。

整理の前と後で同じテストを流し、compare_snapshots.py で比べて「DB に書く内容が変わらない」ことを確かめる。
使い方は quickstart.md。リポジトリのテストには入れない（テストの数を変えないため）。

    PYTHONHASHSEED=0 SNAPSHOT_OUT=/tmp/before.jsonl python -m pytest tests/ -q -p snapshot_plugin

書くもの：
- DB を使うテストは、全テーブルの行（db_session を使うテストだけ）
- すべてのテストで、登録されたスクレイパー（SCRAPER_REGISTRY）の fetch()・parse()・parse_departures() が
  返したもの。テストの多くは parse_departures() の戻り値を見るだけで DB に書かないので、DB だけでは足りない。
  fetch() は raw_html_hash の材料なので、文字列の SHA-256 を書く

実行のたびに変わる時刻の列・キー（作成・更新・取得・確認・開始・終了）と id は書かない。
行の並べ替え・照合は compare_snapshots.py がする（毎回変わる列を落としてから比べるため）。
テストには date.today() から日付を作るものがあるので、取った日（run_date）も書く。比べるときに同じ日か確かめる。
"""

import datetime
import functools
import hashlib
import json
import os

import pytest
from sqlalchemy import text

from scraper.db.models import Base
from scraper.scrapers import SCRAPER_REGISTRY

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

_CAPTURED = ("fetch", "parse", "parse_departures")
# テスト1件のあいだに返したもの：表の名前（"MarueFerry.parse_departures" など）→ 行
_returned: dict[str, list[dict]] = {}
_originals: list[tuple[type, str, object]] = []


def _plain(value):
    if isinstance(value, dict):
        return {k: str(v) for k, v in value.items() if k not in _VOLATILE}
    return {"value": str(value)}


def _wrap(cls: type, name: str):
    method = getattr(cls, name)

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        result = method(self, *args, **kwargs)
        rows = _returned.setdefault(f"{cls.__name__}.{name}", [])
        # 同じテストで何回目の呼び出しか（行の多重集合で比べても、呼び出しの区切りが残るように）
        call = str(sum(1 for r in rows if r["_row"] == "0"))
        if name == "fetch":
            digest = hashlib.sha256(str(result).encode()).hexdigest()
            rows.append({"_call": call, "_row": "0", "sha256": digest})
        elif not result:
            rows.append({"_call": call, "_row": "0", "empty": "1"})
        else:
            for i, rec in enumerate(result):
                rows.append({"_call": call, "_row": str(i), **_plain(rec)})
        return result

    return wrapper


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    if not os.environ.get("SNAPSHOT_OUT"):
        return
    _returned.clear()
    for cls in SCRAPER_REGISTRY.values():
        for name in _CAPTURED:
            _originals.append((cls, name, cls.__dict__.get(name)))
            setattr(cls, name, _wrap(cls, name))


def _restore() -> None:
    while _originals:
        cls, name, original = _originals.pop()
        if original is None:
            delattr(cls, name)
        else:
            setattr(cls, name, original)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_teardown(item, nextitem):
    """フィクスチャの後片付け（db_session の drop_all）より先に読む。"""
    out = os.environ.get("SNAPSHOT_OUT")
    if not out:
        return
    _restore()
    tables: dict[str, list[dict] | str] = {
        f"returned:{k}": v for k, v in sorted(_returned.items())
    }
    session = getattr(item, "funcargs", {}).get("db_session")
    if session is None:
        _write(out, item, tables)
        return
    # 直接 _upsert_departures() を呼ぶテストはコミットしないので、ロールバックせずにそのまま読む。
    # 読めなくなったら（セッションが壊れている）ロールバックはせず、そこから先のテーブルを error にする。
    # ロールバックするとまだコミットしていない行が消え、前後どちらも空で一致してしまう。
    # error は compare_snapshots.py が「確かめられない」として違いに数える
    broken: str | None = None
    # 別の接続を開かない（:memory: の SQLite は接続が1つ）
    for name in sorted(Base.metadata.tables):
        if broken is not None:
            tables[name] = broken
            continue
        try:
            rows = session.execute(text(f"SELECT * FROM {name}")).mappings().all()
        except Exception as e:
            broken = f"error: {type(e).__name__}"
            tables[name] = broken
            continue
        tables[name] = [
            {k: str(v) for k, v in row.items() if k not in _VOLATILE} for row in rows
        ]
    _write(out, item, tables)


def _write(out: str, item, tables: dict) -> None:
    with open(out, "a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "test": item.nodeid,
                    # テストはモジュールの date を差し替えるが datetime モジュールの date は
                    # 差し替えないので、これは本当の今日
                    "run_date": datetime.date.today().isoformat(),
                    "tables": tables,
                },
                sort_keys=True,
                ensure_ascii=False,
            )
            + "\n"
        )
