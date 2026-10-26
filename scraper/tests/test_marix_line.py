"""
MarixLine スクレイパーのユニットテスト。

モックHTML を使用して parse() の動作を検証する。
HTTP リクエストは responses ライブラリでモック。
DBは SQLite in-memory を使用（conftest.py の db_session / marix_line_company フィクスチャ）。
"""

import re

import pytest
import responses as resp_mock
from datetime import date
from unittest.mock import patch, MagicMock

from sqlalchemy import select

from scraper.scrapers.marix_line import MarixLine, SOURCE_URL
from scraper.db.models import OperationStatusEnum, Port, Route, RouteStop


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
    resp_mock.add(
        resp_mock.GET, SOURCE_URL, body=HTML_NORMAL_DOWN_DELAYED_UP, status=200
    )

    scraper = MarixLine(db_session, marix_line_company.id)
    # HTML内日付（2026-03-07）を today に固定して no_service が追加されないようにする
    with patch("scraper.scrapers.marix_line.date", _make_date_mock(date(2026, 3, 7))):
        records = scraper.parse(scraper.fetch())

    routes = (
        db_session.execute(
            select(Route).where(Route.ferry_company_id == marix_line_company.id)
        )
        .scalars()
        .all()
    )
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
    resp_mock.add(
        resp_mock.GET, SOURCE_URL, body=HTML_NORMAL_DOWN_DELAYED_UP, status=200
    )

    scraper = MarixLine(db_session, marix_line_company.id)
    with patch("scraper.scrapers.marix_line.date", _make_date_mock(date(2026, 3, 7))):
        records = scraper.parse(scraper.fetch())

    routes = (
        db_session.execute(
            select(Route).where(Route.ferry_company_id == marix_line_company.id)
        )
        .scalars()
        .all()
    )
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
    operating_recs = [
        r for r in records if r["status"] == OperationStatusEnum.operating
    ]
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
        if r["route_id"] == up_route.id
        and r["status"] == OperationStatusEnum.no_service
    ]
    assert len(up_no_service_recs) == 1
    assert up_no_service_recs[0]["valid_date"] == date(2026, 3, 7)


@resp_mock.activate
def test_date_parsed_from_info2(db_session, marix_line_company):
    """info2 の YYYY年M月D日 が valid_date として正しく解析される。"""
    resp_mock.add(
        resp_mock.GET, SOURCE_URL, body=HTML_NORMAL_DOWN_DELAYED_UP, status=200
    )

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

    routes = (
        db_session.execute(
            select(Route).where(Route.ferry_company_id == marix_line_company.id)
        )
        .scalars()
        .all()
    )
    down = next(r for r in routes if r.origin_port == "鹿児島")
    up = next(r for r in routes if r.origin_port == "那覇")

    no_service_recs = [
        r for r in records if r["status"] == OperationStatusEnum.no_service
    ]
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

    routes = (
        db_session.execute(
            select(Route).where(Route.ferry_company_id == marix_line_company.id)
        )
        .scalars()
        .all()
    )
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
    resp_mock.add(
        resp_mock.GET,
        SOURCE_URL,
        body=list_html or read_fixture("marix/list.html"),
        status=200,
    )
    resp_mock.add(
        resp_mock.GET,
        UP_URL,
        body=up if up is not None else read_fixture("marix/upstream_conditional.html"),
        status=up_status,
    )
    resp_mock.add(
        resp_mock.GET,
        DOWN_URL,
        body=down if down is not None else read_fixture("marix/downstream.html"),
        status=down_status,
    )


def _routes(db_session, company):
    routes = (
        db_session.execute(select(Route).where(Route.ferry_company_id == company.id))
        .scalars()
        .all()
    )
    return next(r for r in routes if r.origin_port == "鹿児島"), next(
        r for r in routes if r.origin_port == "那覇"
    )


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
    assert all(
        r["scheduled_arrival_at"] == datetime(2026, 10, 1, 8, 30) for r in rows.values()
    )
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
        '<span class="port_name">和泊港</span>',
        '<span class="port_name">平土野港</span>',
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
# 航行経路変更・欠航・抜港（実サイト 2026-06-24 / 06-26 の詳細ページ）
# ---------------------------------------------------------------------------


def _list_with_down(ymd: str, next_day: str, classes: str, exp: str) -> str:
    """一覧フィクスチャの下り便（9/30 通常運航）を、別の日付・クラスの便に差し替える。"""
    html = read_fixture("marix/list.html")
    head, sep, up_part = html.partition('<div class="up_stream_services">')
    y, m, d = int(ymd[:4]), int(ymd[4:6]), int(ymd[6:])
    head = (
        head.replace("status_single_cover normal", f"status_single_cover {classes}")
        .replace("status_single normal", f"status_single {classes}")
        .replace("downstream20260930", f"downstream{ymd}")
        .replace("2026年9月30日", f"{y}年{m}月{d}日")
        .replace("2026年10月1日", next_day)
        .replace('<p class="exp">通常運航</p>', f'<p class="exp">{exp}</p>')
    )
    return head + sep + up_part


def _down_url(ymd: str) -> str:
    return f"https://marixline.com/service/downstream{ymd}/"


def _mock_down_voyage(ymd, next_day, classes, exp, down_html):
    resp_mock.add(
        resp_mock.GET,
        SOURCE_URL,
        body=_list_with_down(ymd, next_day, classes, exp),
    )
    resp_mock.add(resp_mock.GET, _down_url(ymd), body=down_html)
    resp_mock.add(
        resp_mock.GET, UP_URL, body=read_fixture("marix/upstream_conditional.html")
    )


def _mock_route_change():
    _mock_down_voyage(
        "20260624",
        "2026年6月25日",
        "route alert",
        "航行経路変更",
        read_fixture("marix/downstream_route_change.html"),
    )


@resp_mock.activate
def test_route_change_voyage_is_delayed_not_cancelled(db_session, marix_line_company):
    """一覧の航行経路変更（route alert）は運航するので、欠航ではなく delayed。"""
    _mock_route_change()
    scraper = MarixLine(db_session, marix_line_company.id)
    with patch("scraper.scrapers.marix_line.date", _make_date_mock(date(2026, 6, 24))):
        records = scraper.parse(scraper.fetch())

    down, _ = _routes(db_session, marix_line_company)
    rec = next(
        r
        for r in records
        if r["route_id"] == down.id and r["valid_date"] == date(2026, 6, 24)
    )
    assert rec["status"] == OperationStatusEnum.delayed
    assert rec["status_detail"] == "航行経路変更"


@resp_mock.activate
def test_departures_route_change_skipped_ports(db_session, marix_line_company):
    """経路変更（鹿児島 → 名瀬）：寄る港は delayed、寄らない港（no_status）は skipped（抜港）。"""
    ports = setup_port_master(db_session, marix_line_company)
    _mock_route_change()
    scraper = MarixLine(db_session, marix_line_company.id)
    with structlog.testing.capture_logs() as logs:
        scraper.fetch()
        records = scraper.parse_departures()

    down, _ = _routes(db_session, marix_line_company)
    rows = _by_port(records, ports, down)
    assert list(rows) == ["鹿児島", "名瀬", "亀徳", "和泊", "与論", "本部"]
    for name in ["鹿児島", "名瀬"]:
        assert rows[name]["status"] == OperationStatusEnum.delayed
        assert "航行経路を「鹿児島 → 名瀬」に変更し運航" in rows[name]["status_detail"]
    for name in ["亀徳", "和泊", "与論", "本部"]:
        assert rows[name]["status"] == OperationStatusEnum.skipped
        assert "寄港しません" in rows[name]["status_detail"]
    assert rows["鹿児島"]["ship_name"] == "クイーンコーラルプラス"
    assert not any(log["event"] == "detail_status_unknown" for log in logs)


@resp_mock.activate
def test_route_level_has_no_skipped_with_route_change(db_session, marix_line_company):
    """航路単位（operation_statuses）には抜港を書かない（FR-011）。"""
    _mock_route_change()
    scraper = MarixLine(db_session, marix_line_company.id)
    with patch("scraper.scrapers.marix_line.date", _make_date_mock(date(2026, 6, 24))):
        records = scraper.parse(scraper.fetch())

    assert records
    assert not any(r["status"] == OperationStatusEnum.skipped for r in records)


@resp_mock.activate
def test_no_status_port_follows_cancelled_voyage(db_session, marix_line_company):
    """一覧の便が欠航なら、詳細ページの一部の港だけ no_status でも抜港にならず欠航（FR-005）。"""
    ports = setup_port_master(db_session, marix_line_company)
    _mock_down_voyage(
        "20260624",
        "2026年6月25日",
        "cancel alert",
        "欠航",
        read_fixture("marix/downstream_route_change.html"),
    )
    scraper = MarixLine(db_session, marix_line_company.id)
    with patch("scraper.scrapers.marix_line.date", _make_date_mock(date(2026, 6, 24))):
        scraper.fetch()
    records = scraper.parse_departures()

    down, _ = _routes(db_session, marix_line_company)
    rows = _by_port(records, ports, down)
    assert not any(r["status"] == OperationStatusEnum.skipped for r in rows.values())
    for name in ["亀徳", "和泊", "与論", "本部"]:
        assert rows[name]["status"] == OperationStatusEnum.cancelled


@resp_mock.activate
def test_departures_cancelled_voyage(db_session, marix_line_company):
    """欠航（cancel alert）の便は全港 cancelled。"""
    ports = setup_port_master(db_session, marix_line_company)
    _mock_down_voyage(
        "20260626",
        "2026年6月27日",
        "cancel alert",
        "欠航",
        read_fixture("marix/downstream_cancel.html"),
    )
    scraper = MarixLine(db_session, marix_line_company.id)
    with patch("scraper.scrapers.marix_line.date", _make_date_mock(date(2026, 6, 26))):
        route_records = scraper.parse(scraper.fetch())
    records = scraper.parse_departures()

    down, _ = _routes(db_session, marix_line_company)
    rec = next(
        r
        for r in route_records
        if r["route_id"] == down.id and r["valid_date"] == date(2026, 6, 26)
    )
    assert rec["status"] == OperationStatusEnum.cancelled
    rows = _by_port(records, ports, down)
    assert len(rows) == 6
    assert all(r["status"] == OperationStatusEnum.cancelled for r in rows.values())
    assert not any(r["status"] == OperationStatusEnum.skipped for r in rows.values())
    assert "欠航のため、船の運航は行いません。" in rows["名瀬"]["status_detail"]
    assert not any(r["status"] == OperationStatusEnum.skipped for r in route_records)


def _list_with_unknown_down_class() -> str:
    return read_fixture("marix/list.html").replace(
        "status_single_cover normal", "status_single_cover delay alert"
    )


def _down_with_unknown_port_class() -> str:
    """下り便の途中港（firstport 以外の normal）を知らないクラスにした詳細ページ。"""
    html = read_fixture("marix/downstream.html").replace(
        'class="single normal"', 'class="single delay alert"'
    )
    assert 'class="single delay alert"' in html
    return html


@resp_mock.activate
def test_unknown_class_voyage_is_unknown_not_cancelled(db_session, marix_line_company):
    """知らないクラス（例：delay alert）の便は欠航にせず unknown。今日以外の日も書く（前回のステータスを残さない）。"""
    _mock_pages(list_html=_list_with_unknown_down_class())
    scraper = MarixLine(db_session, marix_line_company.id)
    with structlog.testing.capture_logs() as logs:
        # 便は 9/30 発。今日（10/1）以外の日でも書かれること
        with patch(
            "scraper.scrapers.marix_line.date", _make_date_mock(date(2026, 10, 1))
        ):
            records = scraper.parse(scraper.fetch())

    down, _ = _routes(db_session, marix_line_company)
    rec = next(
        r
        for r in records
        if r["route_id"] == down.id and r["valid_date"] == date(2026, 9, 30)
    )
    assert rec["status"] == OperationStatusEnum.unknown
    assert rec["status_detail"] == "通常運航"  # 一覧の表示をそのまま残す
    assert any(log["event"] == "unknown_status_class" for log in logs)


@resp_mock.activate
def test_unknown_class_voyage_departures_use_port_classes(
    db_session, marix_line_company
):
    """便のクラスを読めなくても詳細ページを読み、港ごとのクラスで判定する。港も読めなければ unknown。"""
    ports = setup_port_master(db_session, marix_line_company)
    _mock_pages(
        list_html=_list_with_unknown_down_class(),
        down=_down_with_unknown_port_class(),
    )
    scraper = MarixLine(db_session, marix_line_company.id)
    scraper.fetch()
    records = scraper.parse_departures()

    down, _ = _routes(db_session, marix_line_company)
    rows = _by_port(records, ports, down)
    assert len(rows) == 6
    assert rows["鹿児島"]["status"] == OperationStatusEnum.operating  # firstport normal
    for name in ["名瀬", "亀徳", "和泊", "与論", "本部"]:
        assert rows[name]["status"] == OperationStatusEnum.unknown
    assert all(r["ship_name"] == "クイーンコーラルクロス" for r in rows.values())


@resp_mock.activate
def test_unknown_class_voyage_fallback_is_unknown(db_session, marix_line_company):
    """便のクラスを読めず詳細ページも取れないときは、予備ルートの行を unknown で書く。"""
    ports = setup_port_master(db_session, marix_line_company)
    _mock_pages(list_html=_list_with_unknown_down_class(), down_status=500)
    scraper = MarixLine(db_session, marix_line_company.id)
    scraper.fetch()
    records = scraper.parse_departures()

    down, _ = _routes(db_session, marix_line_company)
    rows = _by_port(records, ports, down)
    assert len(rows) == 6
    assert all(r["status"] == OperationStatusEnum.unknown for r in rows.values())


@resp_mock.activate
def test_normal_voyage_notes_not_in_unknown_port_detail(db_session, marix_line_company):
    """通常の便の h2「通常通り運航します。」は、港を読めず unknown になっても理由に入れない。"""
    ports = setup_port_master(db_session, marix_line_company)
    _mock_pages(down=_down_with_unknown_port_class())
    scraper = MarixLine(db_session, marix_line_company.id)
    scraper.fetch()
    records = scraper.parse_departures()

    down, _ = _routes(db_session, marix_line_company)
    rows = _by_port(records, ports, down)
    assert rows["名瀬"]["status"] == OperationStatusEnum.unknown
    assert "通常通り運航します" not in (rows["名瀬"]["status_detail"] or "")


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
        .replace(
            "2026年9月30日 鹿児島新港発 2026年10月1日",
            "2026年12月31日 鹿児島新港発 2027年1月1日",
        )
        .replace("downstream20260930", "downstream20261231")
    )
    down_html = (
        read_fixture("marix/downstream.html")
        .replace("09月30日", "12月31日")
        .replace("10月01日", "01月01日")
    )
    resp_mock.add(resp_mock.GET, SOURCE_URL, body=list_html)
    resp_mock.add(
        resp_mock.GET,
        "https://marixline.com/service/downstream20261231/",
        body=down_html,
    )
    resp_mock.add(
        resp_mock.GET, UP_URL, body=read_fixture("marix/upstream_conditional.html")
    )

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


@resp_mock.activate
def test_fallback_rows_follow_list_status_changes(db_session, marix_line_company):
    """詳細ページが取れない状態が続いても、一覧のステータスの変化は予備ルートの行に反映される。"""
    setup_port_master(db_session, marix_line_company)
    _mock_pages(up_status=404)
    scraper = MarixLine(db_session, marix_line_company.id)
    scraper.fetch()
    scraper._upsert_departures(scraper.parse_departures())
    db_session.commit()

    # 一覧の上り便が 条件付 → 欠航 に変わった（詳細ページは引き続き取れない）
    list_html = read_fixture("marix/list.html").replace(
        "status_single_cover conditional alert", "status_single_cover alert"
    )
    resp_mock.reset()
    _mock_pages(list_html=list_html, up_status=404)
    scraper2 = MarixLine(db_session, marix_line_company.id)
    scraper2.fetch()
    scraper2._upsert_departures(scraper2.parse_departures())
    db_session.commit()

    _, up = _routes(db_session, marix_line_company)
    rows = (
        db_session.query(DepartureStatus)
        .filter(DepartureStatus.route_id == up.id)
        .all()
    )
    assert len(rows) == 6
    assert all(r.status == "cancelled" and r.ship_name == "" for r in rows)


@resp_mock.activate
def test_fallback_does_not_overwrite_detail_rows(db_session, marix_line_company):
    """詳細ページから取れた行がある日・港は、予備ルートで上書きしない。"""
    ports = setup_port_master(db_session, marix_line_company)
    _mock_pages()
    scraper = MarixLine(db_session, marix_line_company.id)
    scraper.fetch()
    scraper._upsert_departures(scraper.parse_departures())
    db_session.commit()

    resp_mock.reset()
    _mock_pages(up_status=404)
    scraper2 = MarixLine(db_session, marix_line_company.id)
    scraper2.fetch()
    scraper2._upsert_departures(scraper2.parse_departures())
    db_session.commit()

    _, up = _routes(db_session, marix_line_company)
    rows = (
        db_session.query(DepartureStatus)
        .filter(DepartureStatus.route_id == up.id)
        .all()
    )
    assert len(rows) == 6
    assert all(r.ship_name == "クイーンコーラルプラス" for r in rows)
    yoron = next(r for r in rows if r.port_id == ports["与論"].id)
    assert yoron.status == "delayed"


def _down_with_naze_delayed():
    """下り便の名瀬の出港が 10/1 05:50 → 10/2 00:30 にずれた詳細ページ。"""
    html, n = re.subn(
        r"10月01日(\s*</span>\s*<span class=\"time\">\s*)05:50",
        r"10月02日\g<1>00:30",
        read_fixture("marix/downstream.html"),
    )
    assert n == 1
    return html


def _run_departures(db_session, company):
    scraper = MarixLine(db_session, company.id)
    scraper.fetch()
    scraper._upsert_departures(scraper.parse_departures())
    db_session.commit()


def _naze_rows(db_session, company, ports):
    down, _ = _routes(db_session, company)
    return sorted(
        (r.departure_date, r.ship_name)
        for r in db_session.query(DepartureStatus).filter(
            DepartureStatus.route_id == down.id,
            DepartureStatus.port_id == ports["名瀬"].id,
        )
    )


@resp_mock.activate
def test_fallback_row_is_removed_when_detail_shifts_date(
    db_session, marix_line_company
):
    """予備ルートで作った行は、詳細ページで出港日がずれても残らない（#22）。"""
    ports = setup_port_master(db_session, marix_line_company)
    _mock_pages(down_status=500)
    _run_departures(db_session, marix_line_company)
    assert _naze_rows(db_session, marix_line_company, ports) == [
        (date(2026, 10, 1), "")
    ]

    resp_mock.reset()
    _mock_pages(down=_down_with_naze_delayed())
    _run_departures(db_session, marix_line_company)

    assert _naze_rows(db_session, marix_line_company, ports) == [
        (date(2026, 10, 2), "クイーンコーラルクロス")
    ]


@resp_mock.activate
def test_fallback_does_not_recreate_row_after_detail_shifted_date(
    db_session, marix_line_company
):
    """詳細ページで出港日がずれた後に詳細ページが取れなくなっても、予備ルートの日付で行を作り直さない。"""
    ports = setup_port_master(db_session, marix_line_company)
    _mock_pages(down=_down_with_naze_delayed())
    _run_departures(db_session, marix_line_company)

    resp_mock.reset()
    _mock_pages(down_status=500)
    _run_departures(db_session, marix_line_company)

    assert _naze_rows(db_session, marix_line_company, ports) == [
        (date(2026, 10, 2), "クイーンコーラルクロス")
    ]


@resp_mock.activate
def test_detail_row_is_removed_when_detail_shifts_date(db_session, marix_line_company):
    """詳細ページの行でも、遅延で出港日がずれたら前の日付の行は消える。"""
    ports = setup_port_master(db_session, marix_line_company)
    _mock_pages()
    with patch("scraper.scrapers.base.datetime") as dt:
        # 10/1 05:50 の出港前に取得した、という状況にする
        dt.now.return_value = datetime(2026, 10, 1, 0, 0)
        _run_departures(db_session, marix_line_company)

        resp_mock.reset()
        _mock_pages(down=_down_with_naze_delayed())
        _run_departures(db_session, marix_line_company)

    assert _naze_rows(db_session, marix_line_company, ports) == [
        (date(2026, 10, 2), "クイーンコーラルクロス")
    ]


@resp_mock.activate
def test_detail_row_is_removed_when_delay_is_announced_after_departure_time(
    db_session, marix_line_company
):
    """名瀬 10/1 05:50 発が、10/1 06:00 に「10/2 00:30 発」へ変更されたとき、10/1 の行は残らない。"""
    ports = setup_port_master(db_session, marix_line_company)
    _mock_pages()
    with patch("scraper.scrapers.base.datetime") as dt:
        dt.now.return_value = datetime(2026, 10, 1, 0, 0)
        _run_departures(db_session, marix_line_company)

        dt.now.return_value = datetime(2026, 10, 1, 6, 0)
        resp_mock.reset()
        _mock_pages(down=_down_with_naze_delayed())
        _run_departures(db_session, marix_line_company)

    assert _naze_rows(db_session, marix_line_company, ports) == [
        (date(2026, 10, 2), "クイーンコーラルクロス")
    ]


OTHER_DOWN_URL = "https://marixline.com/service/downstream20261001/"


def _add_other_voyage_naze_row(db_session, company, ports, ship_name, departure_at):
    """10/1 始発の別の便（一覧には出ていない）の、10/2 名瀬の行を入れる。"""
    down, _ = _routes(db_session, company)
    db_session.add(
        DepartureStatus(
            route_id=down.id,
            port_id=ports["名瀬"].id,
            departure_date=date(2026, 10, 2),
            ship_name=ship_name,
            status="operating",
            scheduled_departure_at=departure_at,
            source_url=OTHER_DOWN_URL,
            content_hash="x" * 64,
        )
    )
    db_session.commit()


@resp_mock.activate
def test_shifted_voyage_keeps_other_voyage_fallback_row(db_session, marix_line_company):
    """出港日がずれた便が、ずれた先の日付にある別の便の予備ルートの行を消さない（#28）。"""
    ports = setup_port_master(db_session, marix_line_company)
    _add_other_voyage_naze_row(db_session, marix_line_company, ports, "", None)

    _mock_pages(down=_down_with_naze_delayed())
    with patch("scraper.scrapers.base.datetime") as dt:
        dt.now.return_value = datetime(2026, 10, 1, 0, 0)
        _run_departures(db_session, marix_line_company)

    assert _naze_rows(db_session, marix_line_company, ports) == [
        (date(2026, 10, 2), ""),
        (date(2026, 10, 2), "クイーンコーラルクロス"),
    ]


@resp_mock.activate
def test_shifted_voyage_keeps_other_voyage_detail_row(db_session, marix_line_company):
    """出港日がずれた便が、ずれた先の日付にある別の便の詳細ページの行を消さない（#28）。"""
    ports = setup_port_master(db_session, marix_line_company)
    _add_other_voyage_naze_row(
        db_session,
        marix_line_company,
        ports,
        "クイーンコーラルプラス",
        datetime(2026, 10, 2, 5, 50),
    )

    _mock_pages(down=_down_with_naze_delayed())
    with patch("scraper.scrapers.base.datetime") as dt:
        dt.now.return_value = datetime(2026, 10, 1, 0, 0)
        _run_departures(db_session, marix_line_company)

    assert _naze_rows(db_session, marix_line_company, ports) == [
        (date(2026, 10, 2), "クイーンコーラルクロス"),
        (date(2026, 10, 2), "クイーンコーラルプラス"),
    ]


# ---------------------------------------------------------------------------
# 臨時便（13-marix-extra-voyages）のテスト用の道具
# 公式の保存版（2026-08〜09）の詳細ページを fixture にする。一覧の HTML は実物が未確認なので、
# 今の list.html と同じ形で組み立てる（research R1）
# ---------------------------------------------------------------------------

EXTRA_DOWN_0906 = "https://marixline.com/service/service6727/"
DOWN_0906 = "https://marixline.com/service/downstream20260906/"
EXTRA_UP_0907 = "https://marixline.com/service/service6731/"
UP_0907 = "https://marixline.com/service/upstream20260907/"
EXTRA_UP_0927 = "https://marixline.com/service/service6819/"
EXTRA_DOWN_0827 = "https://marixline.com/service/service6664/"


def _make_datetime_mock(now: datetime):
    """datetime.now() を now に固定しつつ datetime() コンストラクタも通すモックを作成。"""
    mock = MagicMock(wraps=datetime)
    mock.now.return_value = now
    return mock


def _list_cover(cls: str, url: str, info2: str) -> str:
    if "temporary" in cls:
        exp = "臨時便運航"
    elif "cancel" in cls or cls.split() == ["alert"]:
        exp = "欠航"
    elif "route" in cls:
        exp = "航行経路変更"
    else:
        exp = "通常運航"
    return (
        f'<div class="status_single_cover {cls}">'
        f'<a class="status_single {cls}" href="{url}">'
        f'<div class="info1"><p class="exp">{exp}</p></div>'
        f'<div class="info2">{info2}</div>'
        "</a></div>"
    )


def _list_html(down: list[tuple[str, str, str]], up: list[tuple[str, str, str]]) -> str:
    """一覧の HTML。要素は（便のクラス、詳細ページの URL、info2 の文）。"""
    return (
        '<html><body><div class="service_list">'
        '<div class="down_stream_services">'
        + "".join(_list_cover(*v) for v in down)
        + '</div><div class="up_stream_services">'
        + "".join(_list_cover(*v) for v in up)
        + "</div></div></body></html>"
    )


def _mock_extra_pages(list_html: str, pages: dict[str, "str | int"]) -> None:
    """一覧と、URL → fixture 名（または HTML 本文）／ステータスコードを登録する。"""
    resp_mock.add(resp_mock.GET, SOURCE_URL, body=list_html, status=200)
    for url, page in pages.items():
        if isinstance(page, int):
            resp_mock.add(resp_mock.GET, url, body="error", status=page)
        elif page.endswith(".html") and "\n" not in page:
            resp_mock.add(resp_mock.GET, url, body=read_fixture(f"marix/{page}"))
        else:
            resp_mock.add(resp_mock.GET, url, body=page)


# ---------------------------------------------------------------------------
# 便の種類（research R1）
# ---------------------------------------------------------------------------

_INFO2_DOWN_0906 = "2026年9月6日 鹿児島新港発 2026年9月7日 那覇港 向け"
_INFO2_UP_0907 = "2026年9月7日 那覇港発 2026年9月8日 鹿児島新港 向け"


def _kind_of(db_session, company, cls, url, page, info2, *, fetch=True):
    """一覧に便を1つ置いて fetch() し、その便の種類を返す。"""
    from bs4 import BeautifulSoup

    setup_port_master(db_session, company)
    _mock_extra_pages(
        _list_html([(cls, url, info2)], [])
        if "鹿児島新港発" in info2
        else _list_html([], [(cls, url, info2)]),
        {url: page},
    )
    scraper = MarixLine(db_session, company.id)
    if fetch:
        scraper.fetch()
        html = scraper._list_html
    else:
        html = _list_html([(cls, url, info2)], [])
    block = BeautifulSoup(html, "lxml").select_one("div.status_single_cover")
    detail = scraper._detail_pages.get(url) if fetch else None
    return scraper._voyage_kind(block, detail)


@resp_mock.activate
def test_voyage_kind_list_temporary_class_is_extra(db_session, marix_line_company):
    """一覧の便のクラスが temporary なら、詳細ページが取れなくても臨時便。"""
    kind = _kind_of(
        db_session,
        marix_line_company,
        "temporary alert",
        EXTRA_DOWN_0906,
        500,
        _INFO2_DOWN_0906,
    )
    assert kind == "extra"


@resp_mock.activate
def test_voyage_kind_extra_by_detail_heading(db_session, marix_line_company):
    """一覧のクラスが route alert でも、詳細ページの見出し【臨時便…】で臨時便とわかる。"""
    kind = _kind_of(
        db_session,
        marix_line_company,
        "route alert",
        EXTRA_DOWN_0906,
        "extra_down_20260906.html",
        _INFO2_DOWN_0906,
    )
    assert kind == "extra"


@resp_mock.activate
def test_voyage_kind_extra_by_detail_port_class(db_session, marix_line_company):
    """見出しの【臨時便…】が無くても、港の temporary で臨時便とわかる。"""
    html = read_fixture("marix/extra_up_20260907.html").replace("【臨時便運航】", "")
    assert "【臨時便" not in html and "temporary" in html
    kind = _kind_of(
        db_session,
        marix_line_company,
        "route alert",
        EXTRA_UP_0907,
        html,
        _INFO2_UP_0907,
    )
    assert kind == "extra"


@pytest.mark.parametrize(
    "cls,url,page,info2",
    [
        ("route alert", DOWN_0906, "down_route_change_20260906.html", _INFO2_DOWN_0906),
        ("cancel alert", UP_0907, "up_cancel_20260907.html", _INFO2_UP_0907),
        (
            "normal",
            "https://marixline.com/service/downstream20260930/",
            "downstream.html",
            "2026年9月30日 鹿児島新港発 2026年10月1日 那覇港 向け",
        ),
        (
            "conditional alert",
            "https://marixline.com/service/upstream20260930/",
            "upstream_conditional.html",
            "2026年9月30日 那覇港発 2026年10月1日 鹿児島新港 向け",
        ),
    ],
)
@resp_mock.activate
def test_voyage_kind_regular(db_session, marix_line_company, cls, url, page, info2):
    assert _kind_of(db_session, marix_line_company, cls, url, page, info2) == "regular"


@resp_mock.activate
def test_voyage_kind_unknown_when_detail_missing(db_session, marix_line_company):
    """詳細ページが取れず、一覧に temporary も無い便は「分からない」。"""
    kind = _kind_of(
        db_session,
        marix_line_company,
        "route alert",
        EXTRA_DOWN_0906,
        500,
        _INFO2_DOWN_0906,
    )
    assert kind == "unknown"


@resp_mock.activate
def test_voyage_kind_regular_without_fetch(db_session, marix_line_company):
    """fetch() を通さない呼び方（既存のテスト）では、今までどおり定期便。"""
    kind = _kind_of(
        db_session,
        marix_line_company,
        "route alert",
        EXTRA_DOWN_0906,
        500,
        _INFO2_DOWN_0906,
        fetch=False,
    )
    assert kind == "regular"


# ---------------------------------------------------------------------------
# US2: 臨時便の港が「臨時便」で出る
# ---------------------------------------------------------------------------

CROSS = "クイーンコーラルクロス"
PLUS = "クイーンコーラルプラス"
_EXTRA_DOWN_0906 = ("temporary alert", EXTRA_DOWN_0906, _INFO2_DOWN_0906)
_DOWN_0906 = ("route alert", DOWN_0906, _INFO2_DOWN_0906)
_PAGES_0906 = {
    DOWN_0906: "down_route_change_20260906.html",
    EXTRA_DOWN_0906: "extra_down_20260906.html",
}


def _departures(db_session, company, list_html, pages, today, now=None):
    """一覧と詳細ページを登録して fetch() → parse_departures()。(行, 港, ログ, scraper) を返す。"""
    if db_session.query(RouteStop).count():  # 同じテストで2回呼ぶときは作り直さない
        ports = {p.name: p for p in db_session.query(Port).all()}
    else:
        ports = setup_port_master(db_session, company)
    _mock_extra_pages(list_html, pages)
    scraper = MarixLine(db_session, company.id)
    with (
        patch("scraper.scrapers.marix_line.date", _make_date_mock(today)),
        patch(
            "scraper.scrapers.marix_line.datetime",
            _make_datetime_mock(now or datetime.combine(today, datetime.min.time())),
        ),
        structlog.testing.capture_logs() as logs,
    ):
        scraper.fetch()
        records = scraper.parse_departures()
    return records, ports, logs, scraper


def _rows_for(records, ports, route, port=None, ship=None):
    """route の行を、港名・船名で絞る。"""
    names = {p.id: name for name, p in ports.items()}
    return [
        r
        for r in records
        if r["route_id"] == route.id
        and (port is None or names[r["port_id"]] == port)
        and (ship is None or r["ship_name"] == ship)
    ]


@resp_mock.activate
def test_extra_voyage_writes_extra_row_at_stop(db_session, marix_line_company):
    """臨時便が寄る鹿児島は extra。出港・到着予定は詳細ページどおり（SC-002）。"""
    records, ports, logs, _ = _departures(
        db_session,
        marix_line_company,
        _list_html([_DOWN_0906, _EXTRA_DOWN_0906], []),
        _PAGES_0906,
        date(2026, 9, 6),
    )
    down, _ = _routes(db_session, marix_line_company)

    (row,) = _rows_for(records, ports, down, "鹿児島", CROSS)
    assert row["status"] == OperationStatusEnum.extra
    assert row["departure_date"] == date(2026, 9, 6)
    assert row["scheduled_departure_at"] == datetime(2026, 9, 6, 9, 0)
    assert row["scheduled_arrival_at"] == datetime(2026, 9, 7, 5, 0)
    assert row["source_url"] == EXTRA_DOWN_0906
    assert row["extra_voyage"] is True
    assert "replace_source" not in row or row["replace_source"] is None
    # 臨時便の詳細ページの見出しの文が詳細に入る
    assert (
        "臨時便で時間を変更し、航行経路を「鹿児島 → 那覇」に変更して運航します"
        in row["status_detail"]
    )
    events = {log["event"] for log in logs}
    assert "unknown_status_class" not in events
    assert "detail_status_unknown" not in events


@resp_mock.activate
def test_extra_voyage_does_not_change_regular_voyage_rows(
    db_session, marix_line_company
):
    """同じ日の定期便（プラス）の行は、臨時便を一覧から外して読んだときと同じ。"""
    with_extra, ports, _, _ = _departures(
        db_session,
        marix_line_company,
        _list_html([_DOWN_0906, _EXTRA_DOWN_0906], []),
        _PAGES_0906,
        date(2026, 9, 6),
    )
    down, _ = _routes(db_session, marix_line_company)
    plus_with = _rows_for(with_extra, ports, down, ship=PLUS)

    resp_mock.reset()
    only_regular, _, _, _ = _departures(
        db_session,
        marix_line_company,
        _list_html([_DOWN_0906], []),
        {DOWN_0906: "down_route_change_20260906.html"},
        date(2026, 9, 6),
    )
    plus_only = _rows_for(only_regular, ports, down, ship=PLUS)

    assert plus_with == plus_only
    by_port = {
        name: r["status"]
        for name in ports
        for r in plus_with
        if r["port_id"] == ports[name].id
    }
    assert by_port["名瀬"] == OperationStatusEnum.delayed
    assert by_port["亀徳"] == OperationStatusEnum.delayed
    assert by_port["本部"] == OperationStatusEnum.delayed
    assert by_port["和泊"] == OperationStatusEnum.skipped
    assert by_port["与論"] == OperationStatusEnum.skipped
    assert all(r["extra_voyage"] is False for r in plus_with)


@resp_mock.activate
def test_extra_voyage_own_cancellation_is_cancelled(db_session, marix_line_company):
    """臨時便そのものの欠航（港のクラスが cancel）は cancelled。"""
    page = read_fixture("marix/extra_down_20260906.html").replace(
        "single firstport temporary alert", "single firstport cancel alert"
    )
    assert "firstport cancel alert" in page
    records, ports, _, _ = _departures(
        db_session,
        marix_line_company,
        _list_html([_DOWN_0906, _EXTRA_DOWN_0906], []),
        {**_PAGES_0906, EXTRA_DOWN_0906: page},
        date(2026, 9, 6),
    )
    down, _ = _routes(db_session, marix_line_company)

    (row,) = _rows_for(records, ports, down, "鹿児島", CROSS)
    assert row["status"] == OperationStatusEnum.cancelled


@resp_mock.activate
def test_extra_voyage_without_detail_page_writes_no_rows(
    db_session, marix_line_company
):
    """臨時便の詳細ページが取れなければ、予備ルートも使わず行を作らない（FR-010・R6）。"""
    records, ports, logs, _ = _departures(
        db_session,
        marix_line_company,
        _list_html([_DOWN_0906, _EXTRA_DOWN_0906], []),
        {**_PAGES_0906, EXTRA_DOWN_0906: 500},
        date(2026, 9, 6),
    )
    down, _ = _routes(db_session, marix_line_company)

    assert [r for r in records if r["source_url"] == EXTRA_DOWN_0906] == []
    assert _rows_for(records, ports, down, ship=CROSS) == []
    missing = [log for log in logs if log["event"] == "extra_voyage_detail_missing"]
    assert len(missing) == 1


@resp_mock.activate
def test_unknown_kind_voyage_uses_fallback_route_rows(db_session, marix_line_company):
    """一覧のクラスが route alert で詳細ページが 500（種類が分からない）→ 予備ルートの行（R6）。"""
    records, ports, _, _ = _departures(
        db_session,
        marix_line_company,
        _list_html([("route alert", EXTRA_DOWN_0906, _INFO2_DOWN_0906)], []),
        {EXTRA_DOWN_0906: 500},
        date(2026, 9, 6),
    )
    down, _ = _routes(db_session, marix_line_company)

    rows = [r for r in records if r["source_url"] == EXTRA_DOWN_0906]
    assert {r["port_id"] for r in rows} == {
        ports[n].id for n in ("鹿児島", "名瀬", "亀徳", "和泊", "与論", "本部")
    }
    assert all(r["ship_name"] == "" for r in rows)
    assert all(r["status"] == OperationStatusEnum.delayed for r in rows)
    assert all(r["extra_voyage"] is False for r in rows)
