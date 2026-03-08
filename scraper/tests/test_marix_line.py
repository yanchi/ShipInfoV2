"""
MarixLine スクレイパーのユニットテスト。

モックHTML を使用して parse() の動作を検証する。
HTTP リクエストは responses ライブラリでモック。
DBは SQLite in-memory を使用（conftest.py の db_session / marix_line_company フィクスチャ）。
"""
import responses as resp_mock
from datetime import date
from unittest.mock import patch, MagicMock

from sqlalchemy import select

from scraper.scrapers.marix_line import MarixLine, SOURCE_URL
from scraper.db.models import OperationStatusEnum, Route


def _make_date_mock(today: date):
    """date.today() を today に固定しつつ date() コンストラクタも通すモックを作成。"""
    mock = MagicMock(wraps=date)
    mock.today.return_value = today
    return mock


# ---------------------------------------------------------------------------
# サンプルHTML
# ---------------------------------------------------------------------------

# 下り通常、上り条件付き
HTML_NORMAL_DOWN_DELAYED_UP = """
<html><body>
<div class="status_single_cover normal">
  <a class="status_single normal" href="/service/downstream20260307/">
    <div class="info1">
      <p class="exp">通常運航</p>
    </div>
    <div class="info2">
      2026年3月7日 鹿児島新港発 2026年3月8日 那覇港 向け
    </div>
  </a>
</div>
<div class="status_single_cover conditional alert">
  <a class="status_single conditional alert" href="/service/upstream20260307/">
    <div class="info1">
      <p class="exp">条件付運航</p>
    </div>
    <div class="info2">
      2026年3月7日 那覇港発 2026年3月8日 鹿児島新港 向け
    </div>
  </a>
</div>
</body></html>
"""

# 両方欠航
HTML_BOTH_CANCELLED = """
<html><body>
<div class="status_single_cover alert">
  <a class="status_single alert" href="/service/downstream20260308/">
    <div class="info1">
      <p class="exp">欠航</p>
    </div>
    <div class="info2">
      2026年3月8日 鹿児島新港発 2026年3月9日 那覇港 向け
    </div>
  </a>
</div>
<div class="status_single_cover alert">
  <a class="status_single alert" href="/service/upstream20260308/">
    <div class="info1">
      <p class="exp">欠航</p>
    </div>
    <div class="info2">
      2026年3月8日 那覇港発 2026年3月9日 鹿児島新港 向け
    </div>
  </a>
</div>
</body></html>
"""

# status_single_cover のない無関係な div が混在
HTML_WITH_IRRELEVANT_DIVS = """
<html><body>
<div class="header">ヘッダー</div>
<div class="status_single_cover normal">
  <a class="status_single normal" href="/service/downstream20260307/">
    <div class="info1"><p class="exp">通常運航</p></div>
    <div class="info2">2026年3月7日 鹿児島新港発 2026年3月8日 那覇港 向け</div>
  </a>
</div>
<div class="footer">フッター</div>
</body></html>
"""


# 今日の便なし: 別日（2026-03-07）のブロックのみ、today=2026-03-08
HTML_NO_SERVICE_TODAY = """
<html><body>
<div class="status_single_cover normal">
  <a class="status_single normal" href="/service/downstream20260307/">
    <div class="info1"><p class="exp">通常運航</p></div>
    <div class="info2">2026年3月7日 鹿児島新港発 2026年3月8日 那覇港 向け</div>
  </a>
</div>
<div class="status_single_cover normal">
  <a class="status_single normal" href="/service/upstream20260307/">
    <div class="info1"><p class="exp">通常運航</p></div>
    <div class="info2">2026年3月7日 那覇港発 2026年3月8日 鹿児島新港 向け</div>
  </a>
</div>
</body></html>
"""

# 今日の下りのみあり、上りなし: today=2026-03-08 で下りブロックのみ
HTML_ONLY_DOWN_TODAY = """
<html><body>
<div class="status_single_cover normal">
  <a class="status_single normal" href="/service/downstream20260308/">
    <div class="info1"><p class="exp">通常運航</p></div>
    <div class="info2">2026年3月8日 鹿児島新港発 2026年3月9日 那覇港 向け</div>
  </a>
</div>
</body></html>
"""


# ---------------------------------------------------------------------------
# テスト
# ---------------------------------------------------------------------------

@resp_mock.activate
def test_normal_down_delayed_up(db_session, marix_line_company):
    """下り通常・上り条件付きが個別に保存される。"""
    resp_mock.add(resp_mock.GET, SOURCE_URL, body=HTML_NORMAL_DOWN_DELAYED_UP, status=200)

    scraper = MarixLine(db_session, marix_line_company.id)
    # HTML内日付（2026-03-07）を today に固定して no_service が追加されないようにする
    with patch("scraper.scrapers.marix_line.date", _make_date_mock(date(2026, 3, 7))):
        records = scraper.parse(scraper.fetch())

    routes = db_session.execute(
        select(Route).where(Route.ferry_company_id == marix_line_company.id)
    ).scalars().all()
    down = next(r for r in routes if r.origin_port == "鹿児島")
    up = next(r for r in routes if r.origin_port == "那覇")

    assert len(records) == 2

    rec_down = next(r for r in records if r["route_id"] == down.id)
    rec_up = next(r for r in records if r["route_id"] == up.id)

    assert rec_down["status"] == OperationStatusEnum.operating
    assert rec_down["valid_date"] == date(2026, 3, 7)
    assert rec_down["status_detail"] is None  # 通常運航は detail なし

    assert rec_up["status"] == OperationStatusEnum.delayed
    assert rec_up["valid_date"] == date(2026, 3, 7)
    assert rec_up["status_detail"] == "条件付運航"


@resp_mock.activate
def test_both_cancelled(db_session, marix_line_company):
    """上り・下り両方欠航が保存される。"""
    resp_mock.add(resp_mock.GET, SOURCE_URL, body=HTML_BOTH_CANCELLED, status=200)

    scraper = MarixLine(db_session, marix_line_company.id)
    with patch("scraper.scrapers.marix_line.date", _make_date_mock(date(2026, 3, 8))):
        records = scraper.parse(scraper.fetch())

    assert len(records) == 2
    assert all(r["status"] == OperationStatusEnum.cancelled for r in records)
    assert all(r["valid_date"] == date(2026, 3, 8) for r in records)


@resp_mock.activate
def test_conditional_alert_is_delayed_not_cancelled(db_session, marix_line_company):
    """conditional + alert クラスは cancelled ではなく delayed になる。"""
    resp_mock.add(resp_mock.GET, SOURCE_URL, body=HTML_NORMAL_DOWN_DELAYED_UP, status=200)

    scraper = MarixLine(db_session, marix_line_company.id)
    with patch("scraper.scrapers.marix_line.date", _make_date_mock(date(2026, 3, 7))):
        records = scraper.parse(scraper.fetch())

    routes = db_session.execute(
        select(Route).where(Route.ferry_company_id == marix_line_company.id)
    ).scalars().all()
    up = next(r for r in routes if r.origin_port == "那覇")

    rec_up = next(r for r in records if r["route_id"] == up.id)
    assert rec_up["status"] == OperationStatusEnum.delayed


@resp_mock.activate
def test_irrelevant_divs_ignored(db_session, marix_line_company):
    """status_single_cover クラスを持たない div は無視される。"""
    resp_mock.add(resp_mock.GET, SOURCE_URL, body=HTML_WITH_IRRELEVANT_DIVS, status=200)

    scraper = MarixLine(db_session, marix_line_company.id)
    with patch("scraper.scrapers.marix_line.date", _make_date_mock(date(2026, 3, 7))):
        records = scraper.parse(scraper.fetch())

    # 下り: operating（2026-03-07）、上り: no_service（today=2026-03-07 なのに上りブロックなし）
    assert len(records) == 2
    operating_recs = [r for r in records if r["status"] == OperationStatusEnum.operating]
    assert len(operating_recs) == 1

    # 上りルートが no_service になっていることを明示的に検証する
    routes = (
        db_session.execute(
            select(Route).where(Route.ferry_company_id == marix_line_company.id)
        )
        .scalars()
        .all()
    )
    up_route = next(r for r in routes if r.origin_port == "那覇")

    up_no_service_recs = [
        r
        for r in records
        if r["route_id"] == up_route.id and r["status"] == OperationStatusEnum.no_service
    ]
    assert len(up_no_service_recs) == 1
    assert up_no_service_recs[0]["valid_date"] == date(2026, 3, 7)


@resp_mock.activate
def test_date_parsed_from_info2(db_session, marix_line_company):
    """info2 の YYYY年M月D日 が valid_date として正しく解析される。"""
    resp_mock.add(resp_mock.GET, SOURCE_URL, body=HTML_NORMAL_DOWN_DELAYED_UP, status=200)

    scraper = MarixLine(db_session, marix_line_company.id)
    with patch("scraper.scrapers.marix_line.date", _make_date_mock(date(2026, 3, 7))):
        records = scraper.parse(scraper.fetch())

    # 両ルートとも 2026-03-07（today = 2026-03-07 なので no_service は追加されない）
    assert all(r["valid_date"] == date(2026, 3, 7) for r in records)


@resp_mock.activate
def test_no_service_when_no_block_for_today(db_session, marix_line_company):
    """今日の便ブロックが HTML に存在しない場合、両ルートに no_service が記録される。"""
    resp_mock.add(resp_mock.GET, SOURCE_URL, body=HTML_NO_SERVICE_TODAY, status=200)

    scraper = MarixLine(db_session, marix_line_company.id)
    # today=2026-03-08 だが HTML は 2026-03-07 のブロックのみ
    with patch("scraper.scrapers.marix_line.date", _make_date_mock(date(2026, 3, 8))):
        records = scraper.parse(scraper.fetch())

    routes = db_session.execute(
        select(Route).where(Route.ferry_company_id == marix_line_company.id)
    ).scalars().all()
    down = next(r for r in routes if r.origin_port == "鹿児島")
    up = next(r for r in routes if r.origin_port == "那覇")

    no_service_recs = [r for r in records if r["status"] == OperationStatusEnum.no_service]
    assert len(no_service_recs) == 2

    rec_down = next((r for r in no_service_recs if r["route_id"] == down.id), None)
    rec_up = next((r for r in no_service_recs if r["route_id"] == up.id), None)

    assert rec_down is not None and rec_down["valid_date"] == date(2026, 3, 8)
    assert rec_up is not None and rec_up["valid_date"] == date(2026, 3, 8)
    assert rec_down["status_detail"] is None
    assert rec_up["status_detail"] is None


@resp_mock.activate
def test_no_service_only_for_missing_direction(db_session, marix_line_company):
    """今日の下りブロックのみ存在し上りがない場合、上りのみ no_service が追加される。"""
    resp_mock.add(resp_mock.GET, SOURCE_URL, body=HTML_ONLY_DOWN_TODAY, status=200)

    scraper = MarixLine(db_session, marix_line_company.id)
    with patch("scraper.scrapers.marix_line.date", _make_date_mock(date(2026, 3, 8))):
        records = scraper.parse(scraper.fetch())

    routes = db_session.execute(
        select(Route).where(Route.ferry_company_id == marix_line_company.id)
    ).scalars().all()
    down = next(r for r in routes if r.origin_port == "鹿児島")
    up = next(r for r in routes if r.origin_port == "那覇")

    rec_down = next((r for r in records if r["route_id"] == down.id), None)
    rec_up = next((r for r in records if r["route_id"] == up.id), None)

    assert rec_down is not None and rec_down["status"] == OperationStatusEnum.operating
    assert rec_up is not None and rec_up["status"] == OperationStatusEnum.no_service
    assert rec_up["valid_date"] == date(2026, 3, 8)
    assert rec_up["status_detail"] is None
