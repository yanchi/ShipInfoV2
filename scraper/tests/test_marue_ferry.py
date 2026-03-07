"""
MarueFerry スクレイパーのユニットテスト。

モックHTML を使用して parse() の動作を検証する。
HTTP リクエストは responses ライブラリでモック。
DBは SQLite in-memory を使用（conftest.py の db_session / marue_ferry_company フィクスチャ）。
"""
import responses as resp_mock
from datetime import date

from sqlalchemy import select

from scraper.scrapers.marue_ferry import MarueFerry, SOURCE_URL
from scraper.db.models import OperationStatusEnum, Route


# ---------------------------------------------------------------------------
# サンプルHTML
# ---------------------------------------------------------------------------

# 下り便が条件付き運航（3/6）、通常運航告知（3/7、方向不明）
HTML_DELAYED_DOWN = """
<html><body>
<div class="status-archive">
  <h3>フェリーあけぼの鹿児島 - 名瀬 - 亀徳 - 和泊 - 与論 - 本部 - 那覇</h3>
  <h4>■3/6(金)下り便…条件付き運航</h4>
  <div class="status-detail">
    <div class="tag-list"><span class="tag-conditionally">条件付運航</span></div>
    <p>気象荒天のため条件付き運航</p>
    <p>・条件付寄港地 : 和泊港、与論港</p>
  </div>
  <p>2026年03月07日更新</p>
</div>
<div class="status-archive">
  <h3>フェリー波之上鹿児島 - 名瀬 - 亀徳 - 和泊 - 与論 - 本部 - 那覇</h3>
  <h4>通常運航致しております。</h4>
  <p>2026年03月07日更新</p>
</div>
</body></html>
"""

# 下り・上り両方に明示的なステータス
HTML_BOTH_DIRECTIONS = """
<html><body>
<div class="status-archive">
  <h3>フェリーあけぼの鹿児島 - 那覇</h3>
  <h4>■3/8(日)下り便…欠航</h4>
  <div class="status-detail">
    <p>台風のため欠航</p>
  </div>
  <p>2026年03月07日更新</p>
</div>
<div class="status-archive">
  <h3>フェリーあけぼの鹿児島 - 那覇</h3>
  <h4>■3/8(日)上り便…条件付き運航</h4>
  <div class="status-detail">
    <p>荒天のため条件付き</p>
  </div>
  <p>2026年03月07日更新</p>
</div>
</body></html>
"""


# ---------------------------------------------------------------------------
# テスト
# ---------------------------------------------------------------------------

@resp_mock.activate
def test_delayed_down_fills_up_as_operating(db_session, marue_ferry_company):
    """下り便が delayed のとき、上り便は operating で自動補完される。"""
    resp_mock.add(resp_mock.GET, SOURCE_URL, body=HTML_DELAYED_DOWN, status=200)

    scraper = MarueFerry(db_session, marue_ferry_company.id)
    records = scraper.parse(scraper.fetch())

    routes = db_session.execute(
        select(Route).where(Route.ferry_company_id == marue_ferry_company.id)
    ).scalars().all()
    down = next(r for r in routes if r.origin_port == "鹿児島")
    up = next(r for r in routes if r.origin_port == "那覇")

    # 3/6: 下り delayed, 上り operating（補完）
    rec_306_down = next((r for r in records if r["route_id"] == down.id and r["valid_date"] == date(2026, 3, 6)), None)
    rec_306_up = next((r for r in records if r["route_id"] == up.id and r["valid_date"] == date(2026, 3, 6)), None)

    assert rec_306_down is not None
    assert rec_306_down["status"] == OperationStatusEnum.delayed

    assert rec_306_up is not None, "上り便が operating で自動補完されること"
    assert rec_306_up["status"] == OperationStatusEnum.operating
    assert rec_306_up["status_detail"] is None


@resp_mock.activate
def test_undirected_operating_applies_to_both(db_session, marue_ferry_company):
    """方向不明の通常運航告知は、上り・下り両方に適用される。"""
    resp_mock.add(resp_mock.GET, SOURCE_URL, body=HTML_DELAYED_DOWN, status=200)

    scraper = MarueFerry(db_session, marue_ferry_company.id)
    records = scraper.parse(scraper.fetch())

    routes = db_session.execute(
        select(Route).where(Route.ferry_company_id == marue_ferry_company.id)
    ).scalars().all()
    down = next(r for r in routes if r.origin_port == "鹿児島")
    up = next(r for r in routes if r.origin_port == "那覇")

    # 3/7: 方向不明 → 両方 operating
    rec_307_down = next((r for r in records if r["route_id"] == down.id and r["valid_date"] == date(2026, 3, 7)), None)
    rec_307_up = next((r for r in records if r["route_id"] == up.id and r["valid_date"] == date(2026, 3, 7)), None)

    assert rec_307_down is not None and rec_307_down["status"] == OperationStatusEnum.operating
    assert rec_307_up is not None and rec_307_up["status"] == OperationStatusEnum.operating


@resp_mock.activate
def test_both_directions_explicit(db_session, marue_ferry_company):
    """下り欠航・上り条件付きが個別に保存される。"""
    resp_mock.add(resp_mock.GET, SOURCE_URL, body=HTML_BOTH_DIRECTIONS, status=200)

    scraper = MarueFerry(db_session, marue_ferry_company.id)
    records = scraper.parse(scraper.fetch())

    routes = db_session.execute(
        select(Route).where(Route.ferry_company_id == marue_ferry_company.id)
    ).scalars().all()
    down = next(r for r in routes if r.origin_port == "鹿児島")
    up = next(r for r in routes if r.origin_port == "那覇")

    rec_down = next((r for r in records if r["route_id"] == down.id), None)
    rec_up = next((r for r in records if r["route_id"] == up.id), None)

    assert rec_down is not None and rec_down["status"] == OperationStatusEnum.cancelled
    assert rec_up is not None and rec_up["status"] == OperationStatusEnum.delayed


@resp_mock.activate
def test_status_detail_collected(db_session, marue_ferry_company):
    """status-detail div 内の p テキストが status_detail に格納される。"""
    resp_mock.add(resp_mock.GET, SOURCE_URL, body=HTML_DELAYED_DOWN, status=200)

    scraper = MarueFerry(db_session, marue_ferry_company.id)
    records = scraper.parse(scraper.fetch())

    routes = db_session.execute(
        select(Route).where(Route.ferry_company_id == marue_ferry_company.id)
    ).scalars().all()
    down = next(r for r in routes if r.origin_port == "鹿児島")

    rec = next(r for r in records if r["route_id"] == down.id and r["valid_date"] == date(2026, 3, 6))
    assert "気象荒天のため条件付き運航" in rec["status_detail"]
    assert "和泊港、与論港" in rec["status_detail"]


@resp_mock.activate
def test_no_duplicate_for_same_route_date(db_session, marue_ferry_company):
    """同じ route_id + valid_date の重複レコードは生成されない。"""
    resp_mock.add(resp_mock.GET, SOURCE_URL, body=HTML_DELAYED_DOWN, status=200)

    scraper = MarueFerry(db_session, marue_ferry_company.id)
    records = scraper.parse(scraper.fetch())

    routes = db_session.execute(
        select(Route).where(Route.ferry_company_id == marue_ferry_company.id)
    ).scalars().all()
    down = next(r for r in routes if r.origin_port == "鹿児島")

    recs_307_down = [r for r in records if r["route_id"] == down.id and r["valid_date"] == date(2026, 3, 7)]
    assert len(recs_307_down) == 1, "同日同航路のレコードは1件のみ"
