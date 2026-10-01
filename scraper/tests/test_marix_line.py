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

    # 下り: operating（2026-03-07）、上り: no_service（today=2026-03-07 の上りブロックが存在しない）
    assert len(records) == 2
    operating_recs = [r for r in records if r["status"] == OperationStatusEnum.operating]
    assert len(operating_recs) == 1

    # 上りルートが no_service になっていることを明示的に検証する（今日の上り出発ブロックがHTMLに存在しない）
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


# ---------------------------------------------------------------------------
# 港別（parse_departures）
# ---------------------------------------------------------------------------

from datetime import datetime  # noqa: E402

import structlog  # noqa: E402

from tests.conftest import read_fixture, setup_port_master  # noqa: E402

UP_URL = "https://marixline.com/service/upstream20260930/"
DOWN_URL = "https://marixline.com/service/downstream20260930/"


def _mock_pages(list_html=None, up=None, down=None, up_status=200, down_status=200):
    resp_mock.add(resp_mock.GET, SOURCE_URL, body=list_html or read_fixture("marix/list.html"), status=200)
    resp_mock.add(resp_mock.GET, UP_URL, body=up if up is not None else read_fixture("marix/upstream_conditional.html"), status=up_status)
    resp_mock.add(resp_mock.GET, DOWN_URL, body=down if down is not None else read_fixture("marix/downstream.html"), status=down_status)


def _routes(db_session, company):
    routes = db_session.execute(select(Route).where(Route.ferry_company_id == company.id)).scalars().all()
    return next(r for r in routes if r.origin_port == "鹿児島"), next(r for r in routes if r.origin_port == "那覇")


def _by_port(records, ports, route):
    names = {p.id: name for name, p in ports.items()}
    return {names[r["port_id"]]: r for r in records if r["route_id"] == route.id}


@resp_mock.activate
def test_departures_upstream_conditional_ports(db_session, marix_line_company):
    """上り便：与論・和泊だけ条件付、他は通常運航（US3 シナリオ4・SC-008）。終点の鹿児島は行を作らない。"""
    ports = setup_port_master(db_session, marix_line_company)
    _mock_pages()
    scraper = MarixLine(db_session, marix_line_company.id)
    scraper.fetch()
    records = scraper.parse_departures()

    _, up = _routes(db_session, marix_line_company)
    rows = _by_port(records, ports, up)
    assert list(rows) == ["那覇", "本部", "与論", "和泊", "亀徳", "名瀬"]
    assert rows["与論"]["status"] == OperationStatusEnum.delayed
    assert rows["和泊"]["status"] == OperationStatusEnum.delayed
    for name in ["那覇", "本部", "亀徳", "名瀬"]:
        assert rows[name]["status"] == OperationStatusEnum.operating
        assert rows[name]["status_detail"] is None
    assert "下記の詳細条件を確認してください" in rows["与論"]["status_detail"]
    assert all(r["ship_name"] == "クイーンコーラルプラス" for r in rows.values())
    assert all(r["source_url"] == UP_URL for r in rows.values())
    assert all(r["freeze_after_departure"] is False for r in rows.values())


@resp_mock.activate
def test_departures_times_from_detail(db_session, marix_line_company):
    """出港予定は各港の「出港」、到着予定は終点の「入港」。年は始発日から補う。"""
    ports = setup_port_master(db_session, marix_line_company)
    _mock_pages()
    scraper = MarixLine(db_session, marix_line_company.id)
    scraper.fetch()
    records = scraper.parse_departures()

    _, up = _routes(db_session, marix_line_company)
    rows = _by_port(records, ports, up)
    assert rows["那覇"]["scheduled_departure_at"] == datetime(2026, 9, 30, 7, 0)
    assert rows["与論"]["scheduled_departure_at"] == datetime(2026, 9, 30, 12, 10)
    assert rows["名瀬"]["scheduled_departure_at"] == datetime(2026, 9, 30, 21, 20)
    assert all(r["scheduled_arrival_at"] == datetime(2026, 10, 1, 8, 30) for r in rows.values())
    assert all(r["departure_date"] == date(2026, 9, 30) for r in rows.values())


@resp_mock.activate
def test_departures_port_names_are_normalized(db_session, marix_line_company):
    """「鹿児島新港」「名瀬港」が ports の港に直る。"""
    ports = setup_port_master(db_session, marix_line_company)
    _mock_pages()
    scraper = MarixLine(db_session, marix_line_company.id)
    scraper.fetch()
    records = scraper.parse_departures()

    down, _ = _routes(db_session, marix_line_company)
    rows = _by_port(records, ports, down)
    assert list(rows) == ["鹿児島", "名瀬", "亀徳", "和泊", "与論", "本部"]
    assert rows["鹿児島"]["scheduled_departure_at"] == datetime(2026, 9, 30, 18, 0)
    assert rows["鹿児島"]["ship_name"] == "クイーンコーラルクロス"


@resp_mock.activate
def test_departures_fallback_when_detail_fails(db_session, marix_line_company):
    """詳細ページが取れない便は、便ステータスを全出発港に当てはめ、日付は始発日 + day_offset、時刻は None。"""
    ports = setup_port_master(db_session, marix_line_company)
    _mock_pages(up_status=404)
    scraper = MarixLine(db_session, marix_line_company.id)
    with structlog.testing.capture_logs() as logs:
        scraper.fetch()
        records = scraper.parse_departures()

    _, up = _routes(db_session, marix_line_company)
    rows = _by_port(records, ports, up)
    assert list(rows) == ["那覇", "本部", "与論", "和泊", "亀徳", "名瀬"]
    assert all(r["status"] == OperationStatusEnum.delayed for r in rows.values())
    assert all(r["scheduled_departure_at"] is None for r in rows.values())
    assert all(r["departure_date"] == date(2026, 9, 30) for r in rows.values())
    assert all(r["ship_name"] == "" for r in rows.values())
    assert any(log["event"] == "departure_fallback" for log in logs)


@resp_mock.activate
def test_departures_fallback_uses_day_offset(db_session, marix_line_company):
    """下りの予備ルート：名瀬以降は始発日の翌日。"""
    ports = setup_port_master(db_session, marix_line_company)
    _mock_pages(down_status=500)
    scraper = MarixLine(db_session, marix_line_company.id)
    scraper.fetch()
    records = scraper.parse_departures()

    down, _ = _routes(db_session, marix_line_company)
    rows = _by_port(records, ports, down)
    assert rows["鹿児島"]["departure_date"] == date(2026, 9, 30)
    assert rows["名瀬"]["departure_date"] == date(2026, 10, 1)
    assert rows["本部"]["departure_date"] == date(2026, 10, 1)


@resp_mock.activate
def test_departures_unknown_port_is_ignored(db_session, marix_line_company):
    """寄港順に無い港（平土野）は無視して warning。"""
    ports = setup_port_master(db_session, marix_line_company)
    up_html = read_fixture("marix/upstream_conditional.html").replace(
        '<span class="port_name">和泊港</span>', '<span class="port_name">平土野港</span>'
    )
    assert "平土野港" in up_html
    _mock_pages(up=up_html)
    scraper = MarixLine(db_session, marix_line_company.id)
    with structlog.testing.capture_logs() as logs:
        scraper.fetch()
        records = scraper.parse_departures()

    _, up = _routes(db_session, marix_line_company)
    rows = _by_port(records, ports, up)
    assert "和泊" not in rows
    assert len(rows) == 5
    assert any(log["event"] == "detail_port_not_in_stops" for log in logs)


@resp_mock.activate
def test_route_level_parse_unchanged_with_real_list(db_session, marix_line_company):
    """実際の一覧ページでも航路単位の parse は今までどおり（上り条件付・下り通常）。"""
    setup_port_master(db_session, marix_line_company)
    _mock_pages()
    scraper = MarixLine(db_session, marix_line_company.id)
    with patch("scraper.scrapers.marix_line.date", _make_date_mock(date(2026, 9, 30))):
        records = scraper.parse(scraper.fetch())

    down, up = _routes(db_session, marix_line_company)
    by_route = {r["route_id"]: r for r in records}
    assert by_route[down.id]["status"] == OperationStatusEnum.operating
    assert by_route[up.id]["status"] == OperationStatusEnum.delayed


# ---------------------------------------------------------------------------
# 日またぎ（US5）
# ---------------------------------------------------------------------------

from scraper.db.models import DepartureStatus  # noqa: E402


@resp_mock.activate
def test_downstream_intermediate_ports_depart_next_day(db_session, marix_line_company):
    """9/30 鹿児島発の下り便：名瀬以降の行は 10/1（US5 シナリオ1）。"""
    ports = setup_port_master(db_session, marix_line_company)
    _mock_pages()
    scraper = MarixLine(db_session, marix_line_company.id)
    scraper.fetch()
    records = scraper.parse_departures()

    down, _ = _routes(db_session, marix_line_company)
    rows = _by_port(records, ports, down)
    assert rows["鹿児島"]["departure_date"] == date(2026, 9, 30)
    for name in ["名瀬", "亀徳", "和泊", "与論", "本部"]:
        assert rows[name]["departure_date"] == date(2026, 10, 1)
    assert rows["名瀬"]["scheduled_departure_at"] == datetime(2026, 10, 1, 5, 50)


@resp_mock.activate
def test_year_crossing_voyage(db_session, marix_line_company):
    """12/31 鹿児島発 → 1/1 出港の途中港は翌年の日付になる。"""
    ports = setup_port_master(db_session, marix_line_company)
    list_html = (
        read_fixture("marix/list.html")
        .replace("2026年9月30日 鹿児島新港発 2026年10月1日", "2026年12月31日 鹿児島新港発 2027年1月1日")
        .replace("downstream20260930", "downstream20261231")
    )
    down_html = read_fixture("marix/downstream.html").replace("09月30日", "12月31日").replace("10月01日", "01月01日")
    resp_mock.add(resp_mock.GET, SOURCE_URL, body=list_html)
    resp_mock.add(resp_mock.GET, "https://marixline.com/service/downstream20261231/", body=down_html)
    resp_mock.add(resp_mock.GET, UP_URL, body=read_fixture("marix/upstream_conditional.html"))

    scraper = MarixLine(db_session, marix_line_company.id)
    scraper.fetch()
    records = scraper.parse_departures()

    down, _ = _routes(db_session, marix_line_company)
    rows = _by_port(records, ports, down)
    assert rows["鹿児島"]["scheduled_departure_at"] == datetime(2026, 12, 31, 18, 0)
    assert rows["名瀬"]["departure_date"] == date(2027, 1, 1)
    assert rows["名瀬"]["scheduled_departure_at"] == datetime(2027, 1, 1, 5, 50)
    assert rows["本部"]["scheduled_arrival_at"] == datetime(2027, 1, 1, 19, 0)


@resp_mock.activate
def test_rows_are_kept_after_voyage_leaves_list(db_session, marix_line_company):
    """一覧から消えた便の行は departure_statuses から消さない（FR-013）。"""
    setup_port_master(db_session, marix_line_company)
    _mock_pages()
    scraper = MarixLine(db_session, marix_line_company.id)
    scraper.fetch()
    scraper._upsert_departures(scraper.parse_departures())
    db_session.commit()
    before = db_session.query(DepartureStatus).count()
    assert before == 12

    resp_mock.reset()
    resp_mock.add(resp_mock.GET, SOURCE_URL, body="<html><body></body></html>")
    scraper2 = MarixLine(db_session, marix_line_company.id)
    scraper2.fetch()
    scraper2._upsert_departures(scraper2.parse_departures())
    db_session.commit()

    assert db_session.query(DepartureStatus).count() == before
