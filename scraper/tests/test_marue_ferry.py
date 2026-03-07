"""
MarueFerry スクレイパーのユニットテスト。

モックHTMLを使用して fetch() / parse() の動作を検証する。
HTTP リクエストは responses ライブラリでモック。
DBは SQLite in-memory を使用（conftest.py の db_session / marue_ferry_company フィクスチャ）。
"""
import pytest
import responses as resp_mock
from datetime import date

from bs4 import BeautifulSoup
from sqlalchemy import select

from scraper.scrapers.marue_ferry import MarueFerry, SEARCH_URL, KAGOSHIMA_URL
from scraper.db.models import OperationStatusEnum, Route


# ---------------------------------------------------------------------------
# サンプルHTML
# ---------------------------------------------------------------------------

# 検索エンドポイント: table.s-result が存在しない（サイト構造変更想定）
HTML_SEARCH_NO_TABLE = """
<html><body>
<div class="result-box">
  <div class="responsive-table">
    <!-- table.s-result が欠落 -->
  </div>
</div>
</body></html>
"""

# 検索エンドポイント: 便あり
HTML_SEARCH_HAS_SERVICE = """
<html><body>
<div class="result-box">
  <div class="responsive-table">
    <table class="s-result">
      <thead><tr><th>航路名</th><th>船名</th></tr></thead>
      <tbody>
        <tr>
          <td><a href="../kagoshima">鹿児島航路</a></td>
          <td>フェリーあけぼの</td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
</body></html>
"""

# 検索エンドポイント: 便なし
HTML_SEARCH_NO_SERVICE = """
<html><body>
<div class="result-box">
  <div class="responsive-table">
    <table class="s-result">
      <thead><tr><th>航路名</th><th>船名</th></tr></thead>
      <tbody>
      </tbody>
    </table>
  </div>
</div>
</body></html>
"""

# 鹿児島ページ: 通常運航（実際のHTML構造に合わせる）
HTML_KAGOSHIMA_OPERATING = """
<html><body>
<a href="/status/route-kagoshima/ferry-akebono/1/">
  <div class="route-head">
    <div class="ferry-name">フェリーあけぼの</div>
    <div class="route-detail">鹿児島 - 名瀬 - 亀徳 - 和泊 - 与論 - 本部 - 那覇</div>
  </div>
  <div class="tag-list"><span class="tag-normal">通常運航</span></div>
  <div class="situation-excerpt">通常運航致しております。</div>
</a>
<a href="/status/route-kagoshima/ferry-naminoue/2/">
  <div class="route-head">
    <div class="ferry-name">フェリー波之上</div>
    <div class="route-detail">鹿児島 - 名瀬 - 亀徳 - 和泊 - 与論 - 本部 - 那覇</div>
  </div>
  <div class="tag-list"><span class="tag-normal">通常運航</span></div>
  <div class="situation-excerpt">通常運航致しております。</div>
</a>
</body></html>
"""

# 鹿児島ページ: 条件付き運航
HTML_KAGOSHIMA_DELAYED = """
<html><body>
<a href="/status/route-kagoshima/ferry-akebono/1/">
  <div class="route-head">
    <div class="ferry-name">フェリーあけぼの</div>
    <div class="route-detail">鹿児島 - 名瀬 - 亀徳 - 和泊 - 与論 - 本部 - 那覇</div>
  </div>
  <div class="tag-list"><span class="tag-conditionally">条件付運航</span></div>
  <div class="situation-excerpt">気象荒天のため条件付き運航。和泊港・与論港は条件付寄港。</div>
</a>
</body></html>
"""

# 鹿児島ページ: 欠航
HTML_KAGOSHIMA_CANCELLED = """
<html><body>
<a href="/status/route-kagoshima/ferry-akebono/1/">
  <div class="route-head">
    <div class="ferry-name">フェリーあけぼの</div>
    <div class="route-detail">鹿児島 - 名瀬 - 亀徳 - 和泊 - 与論 - 本部 - 那覇</div>
  </div>
  <div class="tag-list"><span class="tag-cancelled">欠航</span></div>
  <div class="situation-excerpt">台風接近のため欠航いたします。</div>
</a>
</body></html>
"""


# ---------------------------------------------------------------------------
# テスト
# ---------------------------------------------------------------------------

@resp_mock.activate
def test_operating_applies_to_both_routes(db_session, marue_ferry_company):
    """通常運航時、上り・下り両ルートに operating が記録される。"""
    resp_mock.add(resp_mock.POST, SEARCH_URL, body=HTML_SEARCH_HAS_SERVICE, status=200)
    resp_mock.add(resp_mock.GET, KAGOSHIMA_URL, body=HTML_KAGOSHIMA_OPERATING, status=200)

    scraper = MarueFerry(db_session, marue_ferry_company.id)
    records = scraper.parse(scraper.fetch())

    routes = db_session.execute(
        select(Route).where(Route.ferry_company_id == marue_ferry_company.id)
    ).scalars().all()
    down = next(r for r in routes if r.origin_port == "鹿児島")
    up = next(r for r in routes if r.origin_port == "那覇")

    rec_down = next((r for r in records if r["route_id"] == down.id), None)
    rec_up = next((r for r in records if r["route_id"] == up.id), None)

    assert rec_down is not None and rec_down["status"] == OperationStatusEnum.operating
    assert rec_up is not None and rec_up["status"] == OperationStatusEnum.operating


@resp_mock.activate
def test_no_service_records_cancelled_for_both_routes(db_session, marue_ferry_company):
    """本日便なし時、上り・下り両ルートに cancelled が記録される。"""
    resp_mock.add(resp_mock.POST, SEARCH_URL, body=HTML_SEARCH_NO_SERVICE, status=200)

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
    assert rec_up is not None and rec_up["status"] == OperationStatusEnum.cancelled
    assert rec_down["valid_date"] == date.today()
    assert rec_up["valid_date"] == date.today()


@resp_mock.activate
def test_delayed_applies_to_both_routes(db_session, marue_ferry_company):
    """条件付き運航時、上り・下り両ルートに delayed が記録される。"""
    resp_mock.add(resp_mock.POST, SEARCH_URL, body=HTML_SEARCH_HAS_SERVICE, status=200)
    resp_mock.add(resp_mock.GET, KAGOSHIMA_URL, body=HTML_KAGOSHIMA_DELAYED, status=200)

    scraper = MarueFerry(db_session, marue_ferry_company.id)
    records = scraper.parse(scraper.fetch())

    routes = db_session.execute(
        select(Route).where(Route.ferry_company_id == marue_ferry_company.id)
    ).scalars().all()
    down = next(r for r in routes if r.origin_port == "鹿児島")
    up = next(r for r in routes if r.origin_port == "那覇")

    rec_down = next((r for r in records if r["route_id"] == down.id), None)
    rec_up = next((r for r in records if r["route_id"] == up.id), None)

    assert rec_down is not None and rec_down["status"] == OperationStatusEnum.delayed
    assert rec_up is not None and rec_up["status"] == OperationStatusEnum.delayed


@resp_mock.activate
def test_status_detail_collected(db_session, marue_ferry_company):
    """status_detail に鹿児島ページの div.situation-excerpt テキストが格納される。"""
    resp_mock.add(resp_mock.POST, SEARCH_URL, body=HTML_SEARCH_HAS_SERVICE, status=200)
    resp_mock.add(resp_mock.GET, KAGOSHIMA_URL, body=HTML_KAGOSHIMA_DELAYED, status=200)

    scraper = MarueFerry(db_session, marue_ferry_company.id)
    records = scraper.parse(scraper.fetch())

    routes = db_session.execute(
        select(Route).where(Route.ferry_company_id == marue_ferry_company.id)
    ).scalars().all()
    down = next(r for r in routes if r.origin_port == "鹿児島")

    rec = next(r for r in records if r["route_id"] == down.id)
    assert rec["status_detail"] is not None
    assert "気象荒天" in rec["status_detail"]


@resp_mock.activate
def test_cancelled_applies_to_both_routes(db_session, marue_ferry_company):
    """欠航時、上り・下り両ルートに cancelled が記録される。"""
    resp_mock.add(resp_mock.POST, SEARCH_URL, body=HTML_SEARCH_HAS_SERVICE, status=200)
    resp_mock.add(resp_mock.GET, KAGOSHIMA_URL, body=HTML_KAGOSHIMA_CANCELLED, status=200)

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
    assert rec_up is not None and rec_up["status"] == OperationStatusEnum.cancelled


@resp_mock.activate
def test_valid_date_is_today(db_session, marue_ferry_company):
    """valid_date は常に date.today()。"""
    resp_mock.add(resp_mock.POST, SEARCH_URL, body=HTML_SEARCH_HAS_SERVICE, status=200)
    resp_mock.add(resp_mock.GET, KAGOSHIMA_URL, body=HTML_KAGOSHIMA_OPERATING, status=200)

    scraper = MarueFerry(db_session, marue_ferry_company.id)
    records = scraper.parse(scraper.fetch())

    for rec in records:
        assert rec["valid_date"] == date.today()


def test_check_service_returns_true_when_no_result_table(db_session, marue_ferry_company):
    """table.s-result が存在しない HTML でも _check_service() が True を返す（安全側フォールバック）。"""
    scraper = MarueFerry(db_session, marue_ferry_company.id)
    soup = BeautifulSoup(HTML_SEARCH_NO_TABLE, "lxml")
    assert scraper._check_service(soup) is True


@resp_mock.activate
def test_no_duplicate_for_same_route(db_session, marue_ferry_company):
    """複数の div.ferry-name が存在しても、同一ルートのレコードは1件のみ。"""
    resp_mock.add(resp_mock.POST, SEARCH_URL, body=HTML_SEARCH_HAS_SERVICE, status=200)
    resp_mock.add(resp_mock.GET, KAGOSHIMA_URL, body=HTML_KAGOSHIMA_OPERATING, status=200)

    scraper = MarueFerry(db_session, marue_ferry_company.id)
    records = scraper.parse(scraper.fetch())

    routes = db_session.execute(
        select(Route).where(Route.ferry_company_id == marue_ferry_company.id)
    ).scalars().all()
    down = next(r for r in routes if r.origin_port == "鹿児島")

    recs_down = [r for r in records if r["route_id"] == down.id]
    assert len(recs_down) == 1, "同一ルートのレコードは1件のみ"


# 鹿児島ページ: 2船が混在（1隻は通常運航、1隻は欠航）
HTML_KAGOSHIMA_MIXED_OPERATING_CANCELLED = """
<html><body>
<a href="/status/route-kagoshima/ferry-akebono/1/">
  <div class="route-head">
    <div class="ferry-name">フェリーあけぼの</div>
    <div class="route-detail">鹿児島 - 名瀬 - 亀徳 - 和泊 - 与論 - 本部 - 那覇</div>
  </div>
  <div class="tag-list"><span class="tag-normal">通常運航</span></div>
  <div class="situation-excerpt">通常運航致しております。</div>
</a>
<a href="/status/route-kagoshima/ferry-naminoue/2/">
  <div class="route-head">
    <div class="ferry-name">フェリー波之上</div>
    <div class="route-detail">鹿児島 - 名瀬 - 亀徳 - 和泊 - 与論 - 本部 - 那覇</div>
  </div>
  <div class="tag-list"><span class="tag-cancelled">欠航</span></div>
  <div class="situation-excerpt">台風接近のため欠航いたします。</div>
</a>
</body></html>
"""

# 鹿児島ページ: div.ferry-name が存在しない（サイト構造変更で船ブロックが消えた想定）
HTML_KAGOSHIMA_NO_FERRY_BLOCKS = """
<html><body>
<div class="page-content">
  <p>現在、航路情報はありません。</p>
</div>
</body></html>
"""

# 鹿児島ページ: div.ferry-name はあるが div.tag-list span が全てない
HTML_KAGOSHIMA_NO_TAG_SPANS = """
<html><body>
<a href="/status/route-kagoshima/ferry-akebono/1/">
  <div class="route-head">
    <div class="ferry-name">フェリーあけぼの</div>
  </div>
  <div class="tag-list"></div>
  <div class="situation-excerpt">情報なし</div>
</a>
</body></html>
"""


@resp_mock.activate
def test_mixed_ship_statuses_picks_worst_value(db_session, marue_ferry_company):
    """異なるステータスの2船が存在する場合、最悪値（cancelled）が採用され、
    status_detail はその船由来のテキストになる。"""
    resp_mock.add(resp_mock.POST, SEARCH_URL, body=HTML_SEARCH_HAS_SERVICE, status=200)
    resp_mock.add(resp_mock.GET, KAGOSHIMA_URL, body=HTML_KAGOSHIMA_MIXED_OPERATING_CANCELLED, status=200)

    scraper = MarueFerry(db_session, marue_ferry_company.id)
    records = scraper.parse(scraper.fetch())

    routes = db_session.execute(
        select(Route).where(Route.ferry_company_id == marue_ferry_company.id)
    ).scalars().all()
    down = next(r for r in routes if r.origin_port == "鹿児島")
    up = next(r for r in routes if r.origin_port == "那覇")

    rec_down = next((r for r in records if r["route_id"] == down.id), None)
    rec_up = next((r for r in records if r["route_id"] == up.id), None)

    # 最悪値（cancelled）が両ルートに適用される
    assert rec_down is not None and rec_down["status"] == OperationStatusEnum.cancelled
    assert rec_up is not None and rec_up["status"] == OperationStatusEnum.cancelled

    # status_detail は欠航船（フェリー波之上）の situation-excerpt 由来
    assert rec_down["status_detail"] == "台風接近のため欠航いたします。"
    assert rec_up["status_detail"] == "台風接近のため欠航いたします。"


@resp_mock.activate
def test_parse_raises_when_no_ferry_blocks(db_session, marue_ferry_company):
    """has_service=True なのに div.ferry-name が一件もない場合は RuntimeError を送出する。"""
    resp_mock.add(resp_mock.POST, SEARCH_URL, body=HTML_SEARCH_HAS_SERVICE, status=200)
    resp_mock.add(resp_mock.GET, KAGOSHIMA_URL, body=HTML_KAGOSHIMA_NO_FERRY_BLOCKS, status=200)

    scraper = MarueFerry(db_session, marue_ferry_company.id)
    with pytest.raises(RuntimeError, match="no ship statuses parsed"):
        scraper.parse(scraper.fetch())


@resp_mock.activate
def test_parse_raises_when_all_tag_spans_missing(db_session, marue_ferry_company):
    """has_service=True なのに div.tag-list span が全てない場合は RuntimeError を送出する。"""
    resp_mock.add(resp_mock.POST, SEARCH_URL, body=HTML_SEARCH_HAS_SERVICE, status=200)
    resp_mock.add(resp_mock.GET, KAGOSHIMA_URL, body=HTML_KAGOSHIMA_NO_TAG_SPANS, status=200)

    scraper = MarueFerry(db_session, marue_ferry_company.id)
    with pytest.raises(RuntimeError, match="no ship statuses parsed"):
        scraper.parse(scraper.fetch())
