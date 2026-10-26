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
    return scraper._voyage_kind(block, url)


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
    # 臨時便は航路・港を決めない（寄らなくなった港・方向が変わった前の航路の行もルール6で消す）
    assert row["replace_source"] == (None, None, EXTRA_DOWN_0906)
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


# ---------------------------------------------------------------------------
# US3: 臨時便が寄らない港に、臨時便の行を作らない
# ---------------------------------------------------------------------------

_INFO2_UP_0927 = "2026年9月27日 那覇港発 2026年9月27日 鹿児島新港 向け"
_EXTRA_UP_0927 = ("temporary alert", EXTRA_UP_0927, _INFO2_UP_0927)


@resp_mock.activate
def test_extra_voyage_skips_ports_it_does_not_call_at(db_session, marix_line_company):
    """9/6：寄らない名瀬・亀徳・和泊・与論・本部には、臨時便の行も skipped の行も作らない（SC-002）。"""
    records, ports, _, _ = _departures(
        db_session,
        marix_line_company,
        _list_html([_DOWN_0906, _EXTRA_DOWN_0906], []),
        _PAGES_0906,
        date(2026, 9, 6),
    )
    down, _ = _routes(db_session, marix_line_company)

    cross = _rows_for(records, ports, down, ship=CROSS)
    assert [r["port_id"] for r in cross] == [ports["鹿児島"].id]
    # 定期便（プラス）の和泊・与論の skipped は今までどおり（定期便の no_status は変えない）
    plus = {
        r["port_id"]: r["status"] for r in _rows_for(records, ports, down, ship=PLUS)
    }
    assert plus[ports["和泊"].id] == OperationStatusEnum.skipped
    assert plus[ports["与論"].id] == OperationStatusEnum.skipped


@resp_mock.activate
def test_extra_voyage_ignores_stale_dates_of_skipped_ports(
    db_session, marix_line_company
):
    """9/27：寄らない港に残る 08/25 の日付から、2027-08-25 の行を作らない（SC-003 後半）。"""
    records, ports, logs, _ = _departures(
        db_session,
        marix_line_company,
        _list_html([], [_EXTRA_UP_0927]),
        {EXTRA_UP_0927: "extra_up_naze_20260927.html"},
        date(2026, 9, 27),
    )
    _, up = _routes(db_session, marix_line_company)

    rows = _rows_for(records, ports, up)
    assert [(r["port_id"], r["status"]) for r in rows] == [
        (ports["名瀬"].id, OperationStatusEnum.extra)
    ]
    assert not [r for r in rows if r["departure_date"].month == 8]
    assert "detail_stop_missing" not in {log["event"] for log in logs}


# ---------------------------------------------------------------------------
# US3: 臨時便の行の後始末（research R7）。本番と同じ autoflush=False で2回流す
# ---------------------------------------------------------------------------


def _run_extra(db_session, company, list_html, pages, today, now=None):
    """一覧と詳細ページを登録して fetch() → _upsert_departures()。登録は毎回やり直す。"""
    resp_mock.reset()
    if not db_session.query(RouteStop).count():
        setup_port_master(db_session, company)
    _mock_extra_pages(list_html, pages)
    scraper = MarixLine(db_session, company.id)
    with (
        patch("scraper.scrapers.marix_line.date", _make_date_mock(today)),
        patch(
            "scraper.scrapers.marix_line.datetime",
            _make_datetime_mock(now or datetime.combine(today, datetime.min.time())),
        ),
    ):
        scraper.fetch()
        scraper._upsert_departures(scraper.parse_departures())
    db_session.commit()


def _db_rows(db_session, ship=None):
    """DB の行を (港, 出港日, 状態, 船名, source_url) で返す。"""
    names = {p.id: p.name for p in db_session.query(Port).all()}
    return sorted(
        (names[r.port_id], r.departure_date, r.status, r.ship_name, r.source_url)
        for r in db_session.query(DepartureStatus)
        if ship is None or r.ship_name == ship
    )


def _set_port_class(html: str, port: str, classes: list[str]) -> str:
    """詳細ページの港（div.single）のクラスを書き換える。"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for single in soup.select("div.service > div.single"):
        if port in single.select_one("span.port_name").get_text():
            single["class"] = classes
            return str(soup)
    raise AssertionError(port)


def _naze_extra_page() -> str:
    """9/6 の臨時便が、名瀬にも寄る（入港 20:00・出港 20:50）詳細ページ。"""
    return _set_port_class(
        read_fixture("marix/extra_down_20260906.html"),
        "名瀬",
        ["single", "temporary", "alert"],
    )


_ONLY_EXTRA_0906 = _list_html([_EXTRA_DOWN_0906], [])


@resp_mock.activate
def test_extra_rows_removed_when_voyage_stops_calling_at_port(
    db_session, marix_line_company
):
    """US3-3：名瀬に寄らなくなった（no_status）臨時便の名瀬の行が消え、鹿児島の行は残る。"""
    db_session.autoflush = False
    today = date(2026, 9, 6)
    _run_extra(
        db_session,
        marix_line_company,
        _ONLY_EXTRA_0906,
        {EXTRA_DOWN_0906: _naze_extra_page()},
        today,
    )
    assert [r[0] for r in _db_rows(db_session)] == ["名瀬", "鹿児島"]

    _run_extra(
        db_session,
        marix_line_company,
        _ONLY_EXTRA_0906,
        {EXTRA_DOWN_0906: "extra_down_20260906.html"},
        today,
    )
    assert [(r[0], r[2]) for r in _db_rows(db_session)] == [("鹿児島", "extra")]


@resp_mock.activate
def test_extra_row_on_old_date_removed_when_departure_date_shifts(
    db_session, marix_line_company
):
    """臨時便の出港日が 9/6 → 9/7 にずれたら、古い 9/6 の行が消えて 9/7 の行ができる。"""
    db_session.autoflush = False
    today = date(2026, 9, 6)
    _run_extra(
        db_session,
        marix_line_company,
        _ONLY_EXTRA_0906,
        {EXTRA_DOWN_0906: "extra_down_20260906.html"},
        today,
    )
    shifted = re.sub(
        r"09月06日(\s*</span>\s*<span class=\"time\">\s*)09:00",
        r"09月07日\g<1>09:00",
        read_fixture("marix/extra_down_20260906.html"),
    )
    assert "09月07日" in shifted and shifted != read_fixture(
        "marix/extra_down_20260906.html"
    )
    _run_extra(
        db_session,
        marix_line_company,
        _ONLY_EXTRA_0906,
        {EXTRA_DOWN_0906: shifted},
        today,
    )
    assert [(r[0], r[1]) for r in _db_rows(db_session)] == [
        ("鹿児島", date(2026, 9, 7))
    ]


@resp_mock.activate
def test_fallback_rows_of_unknown_kind_removed_when_detail_is_read(
    db_session, marix_line_company
):
    """種類が分からなかった回の予備ルートの行（船名なし）が、読めた回に消える。"""
    db_session.autoflush = False
    today = date(2026, 9, 6)
    _run_extra(
        db_session,
        marix_line_company,
        _list_html([("route alert", EXTRA_DOWN_0906, _INFO2_DOWN_0906)], []),
        {EXTRA_DOWN_0906: 500},
        today,
    )
    first = _db_rows(db_session)
    assert len(first) == 6 and all(r[3] == "" for r in first)

    _run_extra(
        db_session,
        marix_line_company,
        _ONLY_EXTRA_0906,
        {EXTRA_DOWN_0906: "extra_down_20260906.html"},
        today,
    )
    assert [(r[0], r[2], r[3], r[4]) for r in _db_rows(db_session)] == [
        ("鹿児島", "extra", CROSS, EXTRA_DOWN_0906)
    ]


@resp_mock.activate
def test_extra_rows_kept_when_detail_is_not_read(db_session, marix_line_company):
    """2回目に臨時便の詳細ページが取れなければ、1回目の行は全部残る。"""
    db_session.autoflush = False
    today = date(2026, 9, 6)
    _run_extra(
        db_session,
        marix_line_company,
        _ONLY_EXTRA_0906,
        {EXTRA_DOWN_0906: _naze_extra_page()},
        today,
    )
    first = _db_rows(db_session)
    _run_extra(
        db_session,
        marix_line_company,
        _ONLY_EXTRA_0906,
        {EXTRA_DOWN_0906: 500},
        today,
    )
    assert _db_rows(db_session) == first


@resp_mock.activate
def test_cleanup_does_not_touch_regular_voyage_rows(db_session, marix_line_company):
    """定期便（プラス）の行は、臨時便の後始末で変わらない（source_url が違う）。"""
    db_session.autoflush = False
    today = date(2026, 9, 6)
    both = _list_html([_DOWN_0906, _EXTRA_DOWN_0906], [])
    _run_extra(
        db_session,
        marix_line_company,
        both,
        {**_PAGES_0906, EXTRA_DOWN_0906: _naze_extra_page()},
        today,
    )
    plus_before = _db_rows(db_session, PLUS)
    assert plus_before

    _run_extra(db_session, marix_line_company, both, _PAGES_0906, today)
    assert _db_rows(db_session, PLUS) == plus_before
    assert [r[0] for r in _db_rows(db_session, CROSS)] == ["鹿児島"]


# ---------------------------------------------------------------------------
# US1: 欠航の定期便を置き換えた臨時便が出る（research R4・R5）
# ---------------------------------------------------------------------------

_INFO2_UP_0907_EXTRA = "2026年9月7日 那覇港発 2026年9月8日 鹿児島新港 向け"
_CANCEL_UP_0907 = ("cancel alert", UP_0907, _INFO2_UP_0907)
_EXTRA_UP_0907 = ("temporary alert", EXTRA_UP_0907, _INFO2_UP_0907_EXTRA)
_PAGES_0907 = {
    UP_0907: "up_cancel_20260907.html",
    EXTRA_UP_0907: "extra_up_20260907.html",
}


def _list_0907(extra_first: bool, regular=_CANCEL_UP_0907, extra=_EXTRA_UP_0907):
    return _list_html([], [extra, regular] if extra_first else [regular, extra])


def _regular_up_normal_page() -> str:
    """9/7 の定期便が欠航ではなく通常運航の詳細ページ。"""
    from bs4 import BeautifulSoup

    html = read_fixture("marix/up_cancel_20260907.html").replace(
        "【欠航】", "【通常運航】"
    )
    soup = BeautifulSoup(html, "lxml")
    for single in soup.select("div.service > div.single"):
        first = "firstport" in single["class"]
        single["class"] = (
            ["single", "firstport", "normal"] if first else ["single", "normal"]
        )
    return str(soup)


@pytest.mark.parametrize("extra_first", [True, False])
@resp_mock.activate
def test_extra_voyage_wins_over_cancelled_regular_voyage(
    db_session, marix_line_company, extra_first
):
    """SC-001：定期便が欠航のキーは臨時便の行。一覧の並び順に関係なく同じ結果。"""
    records, ports, logs, scraper = _departures(
        db_session,
        marix_line_company,
        _list_0907(extra_first),
        _PAGES_0907,
        date(2026, 9, 7),
    )
    _, up = _routes(db_session, marix_line_company)

    for port, hhmm in (("那覇", (7, 0)), ("名瀬", (21, 20))):
        (row,) = _rows_for(records, ports, up, port, CROSS)
        assert row["status"] == OperationStatusEnum.extra
        assert row["source_url"] == EXTRA_UP_0907
        assert row["scheduled_departure_at"] == datetime(2026, 9, 7, *hhmm)
    for port in ("本部", "与論", "和泊", "亀徳"):
        (row,) = _rows_for(records, ports, up, port, CROSS)
        assert row["status"] == OperationStatusEnum.cancelled
        assert row["source_url"] == UP_0907

    keys = [
        (r["route_id"], r["port_id"], r["departure_date"], r["ship_name"])
        for r in records
    ]
    assert len(keys) == len(set(keys))
    with structlog.testing.capture_logs() as upsert_logs:
        scraper._upsert_departures(records)
    assert "departure_duplicate_key" not in {log["event"] for log in upsert_logs}


@pytest.mark.parametrize("extra_first", [True, False])
@resp_mock.activate
def test_extra_voyage_wins_in_database(db_session, marix_line_company, extra_first):
    """本番と同じ autoflush=False で DB に書いても、1キー1行で臨時便が勝つ。"""
    db_session.autoflush = False
    _run_extra(
        db_session,
        marix_line_company,
        _list_0907(extra_first),
        _PAGES_0907,
        date(2026, 9, 7),
        datetime(2026, 9, 7, 6, 0),
    )
    rows = {(r[0], r[2], r[4]) for r in _db_rows(db_session, CROSS)}
    assert rows == {
        ("那覇", "extra", EXTRA_UP_0907),
        ("名瀬", "extra", EXTRA_UP_0907),
        ("本部", "cancelled", UP_0907),
        ("与論", "cancelled", UP_0907),
        ("和泊", "cancelled", UP_0907),
        ("亀徳", "cancelled", UP_0907),
    }
    assert len(_db_rows(db_session, CROSS)) == 6


@resp_mock.activate
def test_regular_voyage_that_runs_wins_over_extra_voyage(
    db_session, marix_line_company
):
    """FR-006：定期便が走るキーは定期便の行。詳細に「（臨時便 07:00発あり）」と警告を足す。"""
    records, ports, logs, _ = _departures(
        db_session,
        marix_line_company,
        _list_0907(True),
        {**_PAGES_0907, UP_0907: _regular_up_normal_page()},
        date(2026, 9, 7),
    )
    _, up = _routes(db_session, marix_line_company)

    (row,) = _rows_for(records, ports, up, "那覇", CROSS)
    assert row["status"] == OperationStatusEnum.operating
    assert row["source_url"] == UP_0907
    assert row["status_detail"].endswith("（臨時便 07:00発あり）")
    conflicts = [log for log in logs if log["event"] == "extra_voyage_conflict"]
    assert conflicts
    assert all(
        {UP_0907, EXTRA_UP_0907} <= set(map(str, log.values())) for log in conflicts
    )


# 前の回に臨時便が書いた行（research R5）。1回目は 9/7 06:00、定期便（欠航）＋臨時便
_DAY_0907 = date(2026, 9, 7)


def _first_run_0907(db_session, company, pages=None):
    db_session.autoflush = False
    _run_extra(
        db_session,
        company,
        _list_0907(True),
        pages or _PAGES_0907,
        _DAY_0907,
        datetime(2026, 9, 7, 6, 0),
    )


def _up_cross(db_session):
    """上りのクロスの行を (港, 状態, source_url) で返す（那覇・名瀬だけ）。"""
    return [
        (r[0], r[2], r[4])
        for r in _db_rows(db_session, CROSS)
        if r[0] in ("那覇", "名瀬")
    ]


@resp_mock.activate
def test_extra_rows_kept_when_detail_page_not_read(db_session, marix_line_company):
    """US1-4：臨時便が一覧にあり詳細ページが取れない回、定期便（欠航）が上書きしない。"""
    _first_run_0907(db_session, marix_line_company)
    _run_extra(
        db_session,
        marix_line_company,
        _list_0907(True),
        {**_PAGES_0907, EXTRA_UP_0907: 500},
        _DAY_0907,
        datetime(2026, 9, 7, 6, 30),
    )
    assert _up_cross(db_session) == [
        ("名瀬", "extra", EXTRA_UP_0907),
        ("那覇", "extra", EXTRA_UP_0907),
    ]


@resp_mock.activate
def test_extra_rows_kept_for_whole_voyage_after_departure(
    db_session, marix_line_company
):
    """US1-5：始発港を出港した後に一覧から消えても、まだ寄っていない名瀬も含めて上書きしない。"""
    _first_run_0907(db_session, marix_line_company)
    _run_extra(
        db_session,
        marix_line_company,
        _list_html([], [_CANCEL_UP_0907]),
        _PAGES_0907,
        _DAY_0907,
        datetime(2026, 9, 7, 8, 0),
    )
    assert _up_cross(db_session) == [
        ("名瀬", "extra", EXTRA_UP_0907),
        ("那覇", "extra", EXTRA_UP_0907),
    ]


@resp_mock.activate
def test_cancelled_regular_returns_when_extra_vanishes_before_departure(
    db_session, marix_line_company
):
    """US1-6：出港前に臨時便が一覧から消えたら、定期便の欠航に戻る。"""
    _first_run_0907(db_session, marix_line_company)
    _run_extra(
        db_session,
        marix_line_company,
        _list_html([], [_CANCEL_UP_0907]),
        _PAGES_0907,
        _DAY_0907,
        datetime(2026, 9, 7, 6, 30),
    )
    assert _up_cross(db_session) == [
        ("名瀬", "cancelled", UP_0907),
        ("那覇", "cancelled", UP_0907),
    ]


@resp_mock.activate
def test_old_date_returns_to_cancelled_when_extra_shifts_date(
    db_session, marix_line_company
):
    """臨時便の日付がずれたら、古い日付の行は定期便の欠航に戻り、新しい日付に extra の行ができる。"""
    _first_run_0907(db_session, marix_line_company)
    shifted = re.sub(
        r"09月07日(\s*</span>\s*<span class=\"time\">\s*)(07:00|17:00|21:20)",
        r"09月08日\g<1>\g<2>",
        read_fixture("marix/extra_up_20260907.html"),
    )
    _run_extra(
        db_session,
        marix_line_company,
        _list_0907(True),
        {**_PAGES_0907, EXTRA_UP_0907: shifted},
        _DAY_0907,
        datetime(2026, 9, 7, 6, 30),
    )
    rows = {(r[0], r[1], r[2], r[4]) for r in _db_rows(db_session, CROSS)}
    assert ("那覇", date(2026, 9, 7), "cancelled", UP_0907) in rows
    assert ("名瀬", date(2026, 9, 7), "cancelled", UP_0907) in rows
    assert ("那覇", date(2026, 9, 8), "extra", EXTRA_UP_0907) in rows
    assert ("名瀬", date(2026, 9, 8), "extra", EXTRA_UP_0907) in rows


@resp_mock.activate
def test_regular_voyage_that_runs_replaces_vanished_extra(
    db_session, marix_line_company
):
    """定期便が走る回は、臨時便が一覧から消えていても定期便の行（運航）になる。"""
    _first_run_0907(db_session, marix_line_company)
    _run_extra(
        db_session,
        marix_line_company,
        _list_html([], [_CANCEL_UP_0907]),
        {UP_0907: _regular_up_normal_page()},
        _DAY_0907,
        datetime(2026, 9, 7, 6, 30),
    )
    assert ("那覇", "operating", UP_0907) in _up_cross(db_session)


@resp_mock.activate
def test_extra_rows_kept_when_voyage_crosses_midnight(db_session, marix_line_company):
    """日をまたぐ臨時便：始発港（9/6 23:00）で出港済みとみて、名瀬（9/7 21:20）の行も守る。"""
    db_session.autoflush = False
    left_early = re.sub(
        r"09月07日(\s*</span>\s*<span class=\"time\">\s*)07:00",
        r"09月06日\g<1>23:00",
        read_fixture("marix/extra_up_20260907.html"),
    )
    assert "09月06日" in left_early
    _run_extra(
        db_session,
        marix_line_company,
        _list_html(
            [],
            [
                (
                    "temporary alert",
                    EXTRA_UP_0907,
                    "2026年9月6日 那覇港発 2026年9月8日 鹿児島新港 向け",
                ),
                _CANCEL_UP_0907,
            ],
        ),
        {**_PAGES_0907, EXTRA_UP_0907: left_early},
        date(2026, 9, 6),
        datetime(2026, 9, 6, 6, 0),
    )
    assert ("名瀬", "extra", EXTRA_UP_0907) in _up_cross(db_session)

    # 2回目：臨時便は一覧から消え、一覧の便の始発日は 9/7 だけ
    _run_extra(
        db_session,
        marix_line_company,
        _list_html([], [_CANCEL_UP_0907]),
        _PAGES_0907,
        _DAY_0907,
        datetime(2026, 9, 7, 8, 0),
    )
    assert ("名瀬", "extra", EXTRA_UP_0907) in _up_cross(db_session)


@resp_mock.activate
def test_regular_fallback_rows_are_still_written_next_to_extra_rows(
    db_session, marix_line_company
):
    """SC-008 前半：定期便の詳細ページが取れない回も、予備ルートの行は今までどおり作る。"""
    records, ports, _, _ = _departures(
        db_session,
        marix_line_company,
        _list_html([_DOWN_0906, _EXTRA_DOWN_0906], []),
        {**_PAGES_0906, DOWN_0906: 500},
        date(2026, 9, 6),
    )
    down, _ = _routes(db_session, marix_line_company)

    (fallback,) = _rows_for(records, ports, down, "鹿児島", "")
    assert fallback["status"] == OperationStatusEnum.delayed
    assert fallback["source_url"] == DOWN_0906
    (extra,) = _rows_for(records, ports, down, "鹿児島", CROSS)
    assert extra["status"] == OperationStatusEnum.extra


@resp_mock.activate
def test_regular_fallback_rows_removed_once_extra_wins(db_session, marix_line_company):
    """SC-008 後半：次の回に定期便の詳細ページが取れ、臨時便が勝つと、船名なしの行は消える。"""
    db_session.autoflush = False
    _run_extra(
        db_session,
        marix_line_company,
        _list_0907(True),
        {**_PAGES_0907, UP_0907: 500},
        _DAY_0907,
        datetime(2026, 9, 7, 6, 0),
    )
    first = [r for r in _db_rows(db_session) if r[0] in ("那覇", "名瀬")]
    assert {r[3] for r in first} == {"", CROSS}  # 予備ルートの行と臨時便の行が並ぶ

    _run_extra(
        db_session,
        marix_line_company,
        _list_0907(True),
        _PAGES_0907,
        _DAY_0907,
        datetime(2026, 9, 7, 6, 30),
    )
    assert [
        (r[0], r[2], r[3]) for r in _db_rows(db_session) if r[0] in ("那覇", "名瀬")
    ] == [("名瀬", "extra", CROSS), ("那覇", "extra", CROSS)]


# ---------------------------------------------------------------------------
# US4: 途中の港から出る臨時便の方向（research R2）
# ---------------------------------------------------------------------------

_INFO2_NAZE_0927 = "2026年9月27日 名瀬港発 2026年9月27日 鹿児島新港 向け"
_DAY_0927 = date(2026, 9, 27)


@resp_mock.activate
def test_naze_departure_extra_voyage_direction_from_column(
    db_session, marix_line_company
):
    """上りの欄の「名瀬港発 鹿児島新港向け」：上りの名瀬（9/27 05:50）が extra。鹿児島の行は無い。"""
    records, ports, logs, _ = _departures(
        db_session,
        marix_line_company,
        _list_html([], [("temporary alert", EXTRA_UP_0927, _INFO2_NAZE_0927)]),
        {EXTRA_UP_0927: "extra_up_naze_20260927.html"},
        _DAY_0927,
    )
    _, up = _routes(db_session, marix_line_company)

    rows = _rows_for(records, ports, up)
    assert [(r["port_id"], r["status"]) for r in rows] == [
        (ports["名瀬"].id, OperationStatusEnum.extra)
    ]
    assert rows[0]["scheduled_departure_at"] == datetime(2026, 9, 27, 5, 50)
    assert "direction_unknown" not in {log["event"] for log in logs}


def _bare_cover_list(info2: str) -> str:
    """欄（down/up_stream_services）の無い一覧。"""
    return (
        "<html><body>"
        + _list_cover("temporary alert", EXTRA_UP_0927, info2)
        + "</body></html>"
    )


@resp_mock.activate
def test_direction_from_destination_when_no_column(db_session, marix_line_company):
    """欄が無くても、行き先「鹿児島新港 向け」で上りとわかる。結果は欄があるときと同じ。"""
    records, ports, _, _ = _departures(
        db_session,
        marix_line_company,
        _bare_cover_list(_INFO2_NAZE_0927),
        {EXTRA_UP_0927: "extra_up_naze_20260927.html"},
        _DAY_0927,
    )
    _, up = _routes(db_session, marix_line_company)

    assert [(r["port_id"], r["status"]) for r in _rows_for(records, ports, up)] == [
        (ports["名瀬"].id, OperationStatusEnum.extra)
    ]


@resp_mock.activate
def test_direction_unknown_without_column_or_destination(
    db_session, marix_line_company
):
    """欄も始発港も行き先も無ければ、direction_unknown を出して読み飛ばす（今のまま）。"""
    records, _, _, scraper = _departures(
        db_session,
        marix_line_company,
        _bare_cover_list("2026年9月27日 名瀬港発"),
        {EXTRA_UP_0927: "extra_up_naze_20260927.html"},
        _DAY_0927,
    )
    assert records == []
    with structlog.testing.capture_logs() as logs:
        scraper.parse(scraper._list_html)
    assert "direction_unknown" in {log["event"] for log in logs}


# ---------------------------------------------------------------------------
# US5: 航路単位（トップのバッジ）は定期便で決まる（research R8）
# ---------------------------------------------------------------------------


def _route_level(db_session, company, list_html, pages, today):
    """一覧と詳細ページを登録して fetch() → parse()。(行, ログ, 下り, 上り) を返す。"""
    setup_port_master(db_session, company)
    _mock_extra_pages(list_html, pages)
    scraper = MarixLine(db_session, company.id)
    with (
        patch("scraper.scrapers.marix_line.date", _make_date_mock(today)),
        structlog.testing.capture_logs() as logs,
    ):
        records = scraper.parse(scraper.fetch())
    down, up = _routes(db_session, company)
    return records, logs, down, up


def _status_of(records, route, day):
    """その航路・日付の行のステータス（1行だけのはず）。無ければ None。"""
    found = [
        r["status"]
        for r in records
        if r["route_id"] == route.id and r["valid_date"] == day
    ]
    assert len(found) <= 1
    return found[0] if found else None


@pytest.mark.parametrize("extra_first", [True, False])
@resp_mock.activate
def test_route_level_down_0906_ignores_extra_voyage(
    db_session, marix_line_company, extra_first
):
    """9/6 下り：定期便（航行経路変更）が delayed。臨時便が先でも「不明」にならない（SC-004）。"""
    voyages = (
        [_EXTRA_DOWN_0906, _DOWN_0906]
        if extra_first
        else [_DOWN_0906, _EXTRA_DOWN_0906]
    )
    records, logs, down, _ = _route_level(
        db_session,
        marix_line_company,
        _list_html(voyages, []),
        _PAGES_0906,
        date(2026, 9, 6),
    )

    assert _status_of(records, down, date(2026, 9, 6)) == OperationStatusEnum.delayed
    assert OperationStatusEnum.unknown not in {r["status"] for r in records}
    assert "unknown_status_class" not in {log["event"] for log in logs}


@pytest.mark.parametrize("extra_first", [True, False])
@resp_mock.activate
def test_route_level_up_0907_is_cancelled_with_extra_voyage(
    db_session, marix_line_company, extra_first
):
    """9/7 上り：定期便が欠航なので航路単位は cancelled（臨時便は書かない）。"""
    records, _, _, up = _route_level(
        db_session, marix_line_company, _list_0907(extra_first), _PAGES_0907, _DAY_0907
    )

    assert _status_of(records, up, _DAY_0907) == OperationStatusEnum.cancelled


@resp_mock.activate
def test_route_level_extra_only_day_is_no_service(db_session, marix_line_company):
    """臨時便しか無い今日は、今までどおり no_service（extra の行は返さない）。"""
    records, _, _, up = _route_level(
        db_session,
        marix_line_company,
        _list_html([], [("temporary alert", EXTRA_UP_0927, _INFO2_NAZE_0927)]),
        {EXTRA_UP_0927: "extra_up_naze_20260927.html"},
        _DAY_0927,
    )

    assert _status_of(records, up, _DAY_0927) == OperationStatusEnum.no_service


@resp_mock.activate
def test_route_level_extra_found_by_detail_page_when_list_class_is_regular(
    db_session, marix_line_company
):
    """一覧に temporary が無くても、詳細ページで臨時便とわかれば航路単位に書かない（R1）。"""
    records, _, down, _ = _route_level(
        db_session,
        marix_line_company,
        _list_html(
            [("route alert", EXTRA_DOWN_0906, _INFO2_DOWN_0906), _DOWN_0906], []
        ),
        _PAGES_0906,
        date(2026, 9, 6),
    )

    assert _status_of(records, down, date(2026, 9, 6)) == OperationStatusEnum.delayed
    assert OperationStatusEnum.extra not in {r["status"] for r in records}


@resp_mock.activate
def test_route_level_never_returns_extra_status(db_session, marix_line_company):
    """operation_statuses の ENUM に extra は無いので、parse() は extra を返さない。"""
    records, _, _, _ = _route_level(
        db_session, marix_line_company, _list_0907(True), _PAGES_0907, _DAY_0907
    )
    assert OperationStatusEnum.extra not in {r["status"] for r in records}


@resp_mock.activate
def test_route_level_unreadable_unknown_voyage_writes_nothing(
    db_session, marix_line_company
):
    """SC-009：一覧のクラスが読めず詳細ページも取れない便だけの日は、航路単位を書かない。"""
    records, logs, _, up = _route_level(
        db_session,
        marix_line_company,
        _list_html([], [("foo alert", EXTRA_UP_0907, _INFO2_UP_0907)]),
        {EXTRA_UP_0907: 500},
        _DAY_0907,
    )

    assert _status_of(records, up, _DAY_0907) is None
    assert len([log for log in logs if log["event"] == "voyage_kind_unknown"]) == 1


@resp_mock.activate
def test_route_level_readable_unknown_voyage_is_fallback_row(
    db_session, marix_line_company
):
    """一覧のクラスが読めれば、詳細ページが取れなくても今までどおり書く（控えの行）。"""
    records, _, _, up = _route_level(
        db_session,
        marix_line_company,
        _list_html([], [("route alert", EXTRA_UP_0907, _INFO2_UP_0907)]),
        {EXTRA_UP_0907: 500},
        _DAY_0907,
    )

    assert _status_of(records, up, _DAY_0907) == OperationStatusEnum.delayed


@pytest.mark.parametrize("unknown_cls", ["route alert", "foo alert"])
@pytest.mark.parametrize("unknown_first", [True, False])
@resp_mock.activate
def test_route_level_regular_voyage_beats_unknown_voyage(
    db_session, marix_line_company, unknown_cls, unknown_first
):
    """分からない便が一覧で先でも、同じ日の定期便があれば定期便で書く。"""
    unknown = (unknown_cls, EXTRA_UP_0907, _INFO2_UP_0907)
    voyages = (
        [unknown, _CANCEL_UP_0907] if unknown_first else [_CANCEL_UP_0907, unknown]
    )
    records, _, _, up = _route_level(
        db_session,
        marix_line_company,
        _list_html([], voyages),
        {UP_0907: "up_cancel_20260907.html", EXTRA_UP_0907: 500},
        _DAY_0907,
    )

    assert _status_of(records, up, _DAY_0907) == OperationStatusEnum.cancelled


@resp_mock.activate
def test_run_writes_route_level_and_extra_rows_for_0907(db_session, marix_line_company):
    """SC-005：9/7 の一覧（定期便の欠航＋臨時便）を run() で DB に書く。

    航路単位は欠航、那覇・名瀬のクロスは臨時便。トップ・通知メールは、12 の既存テスト
    （testIndexCardShowsExtraDepartureUnderRouteBadge・testStatusTextForExtraPorts・
    testExtraPortsAreLabeledExtra）と同じ形の行から出る。
    """
    from scraper.db.models import OperationStatus

    db_session.autoflush = False
    setup_port_master(db_session, marix_line_company)
    _mock_extra_pages(_list_0907(True), _PAGES_0907)
    scraper = MarixLine(db_session, marix_line_company.id)
    with (
        patch("scraper.scrapers.marix_line.date", _make_date_mock(_DAY_0907)),
        patch(
            "scraper.scrapers.marix_line.datetime",
            _make_datetime_mock(datetime(2026, 9, 7, 6, 0)),
        ),
    ):
        scraper.run()
    db_session.commit()

    _, up = _routes(db_session, marix_line_company)
    route_rows = db_session.query(OperationStatus).filter_by(route_id=up.id).all()
    assert [(r.valid_date, r.status) for r in route_rows] == [
        (_DAY_0907, OperationStatusEnum.cancelled)
    ]
    assert _up_cross(db_session) == [
        ("名瀬", "extra", EXTRA_UP_0907),
        ("那覇", "extra", EXTRA_UP_0907),
    ]


# ---------------------------------------------------------------------------
# PR #90 レビュー：temporary は状態ではなく便の種類
# ---------------------------------------------------------------------------


@resp_mock.activate
def test_extra_port_with_state_class_keeps_the_state(db_session, marix_line_company):
    """臨時便の港が `temporary cancel alert` なら、unknown ではなく cancelled（臨時便そのものの欠航）。"""
    page = _set_port_class(
        read_fixture("marix/extra_down_20260906.html"),
        "鹿児島",
        ["single", "firstport", "temporary", "cancel", "alert"],
    )
    records, ports, logs, _ = _departures(
        db_session,
        marix_line_company,
        _list_html([_EXTRA_DOWN_0906], []),
        {EXTRA_DOWN_0906: page},
        date(2026, 9, 6),
    )
    down, _ = _routes(db_session, marix_line_company)

    (row,) = _rows_for(records, ports, down, "鹿児島", CROSS)
    assert row["status"] == OperationStatusEnum.cancelled
    assert "detail_status_unknown" not in {log["event"] for log in logs}


@resp_mock.activate
def test_voyage_kind_regular_when_only_one_port_is_temporary(
    db_session, marix_line_company
):
    """定期便が1港だけ臨時寄港（temporary）しても、見出しが臨時便でなければ定期便。"""
    page = _set_port_class(
        read_fixture("marix/down_route_change_20260906.html"),
        "本部",
        ["single", "temporary", "alert"],
    )
    assert (
        _kind_of(
            db_session,
            marix_line_company,
            "route alert",
            DOWN_0906,
            page,
            _INFO2_DOWN_0906,
        )
        == "regular"
    )


@resp_mock.activate
def test_unread_extra_rows_removed_when_extra_vanishes_before_departure(
    db_session, marix_line_company
):
    """臨時便だけの日：出港前に一覧から消えたら、同じキーの定期便が無くても「臨時便」の行を消す。"""
    db_session.autoflush = False
    _run_extra(
        db_session,
        marix_line_company,
        _list_html([], [_EXTRA_UP_0907]),
        {EXTRA_UP_0907: "extra_up_20260907.html"},
        _DAY_0907,
        datetime(2026, 9, 7, 6, 0),
    )
    assert _up_cross(db_session)
    _run_extra(
        db_session,
        marix_line_company,
        _list_html([], []),
        {},
        _DAY_0907,
        datetime(2026, 9, 7, 6, 30),
    )
    assert _up_cross(db_session) == []


@resp_mock.activate
def test_unread_extra_rows_kept_when_extra_vanishes_after_departure(
    db_session, marix_line_company
):
    """出港後に一覧から消えた臨時便の行は、便ごと残す。"""
    db_session.autoflush = False
    _run_extra(
        db_session,
        marix_line_company,
        _list_html([], [_EXTRA_UP_0907]),
        {EXTRA_UP_0907: "extra_up_20260907.html"},
        _DAY_0907,
        datetime(2026, 9, 7, 6, 0),
    )
    first = _up_cross(db_session)
    _run_extra(
        db_session,
        marix_line_company,
        _list_html([], []),
        {},
        _DAY_0907,
        datetime(2026, 9, 7, 8, 0),
    )
    assert _up_cross(db_session) == first


# ---------------------------------------------------------------------------
# PR #90 レビュー（2回目）
# ---------------------------------------------------------------------------


def _plus_page_with_motobu(classes: list[str]) -> str:
    return _set_port_class(
        read_fixture("marix/down_route_change_20260906.html"), "本部", classes
    )


@resp_mock.activate
def test_regular_voyage_temporary_port_is_not_extra_and_later_cancel_shows(
    db_session, marix_line_company
):
    """定期便が1港だけ臨時寄港（temporary）しても、その港は臨時便の行にならない。次の欠航も出る。"""
    db_session.autoflush = False
    today = date(2026, 9, 6)
    regular_only = _list_html([_DOWN_0906], [])
    _run_extra(
        db_session,
        marix_line_company,
        regular_only,
        {DOWN_0906: _plus_page_with_motobu(["single", "temporary", "alert"])},
        today,
        datetime(2026, 9, 6, 6, 0),
    )
    first = {r[0]: r[2] for r in _db_rows(db_session, PLUS)}
    assert first["本部"] == "operating"  # 臨時便の行（extra）ではない

    _run_extra(
        db_session,
        marix_line_company,
        regular_only,
        {DOWN_0906: _plus_page_with_motobu(["single", "cancel", "alert"])},
        today,
        datetime(2026, 9, 6, 6, 30),
    )
    second = {r[0]: r[2] for r in _db_rows(db_session, PLUS)}
    assert second["本部"] == "cancelled"


def _null_departure_times(db_session):
    from sqlalchemy import update

    db_session.execute(update(DepartureStatus).values(scheduled_departure_at=None))
    db_session.commit()


@resp_mock.activate
def test_vanished_extra_without_times_is_removed_when_date_is_future(
    db_session, marix_line_company
):
    """出港予定が全部 NULL の臨時便は、出港日が今日より後なら未出港として、一覧から消えたら消す。"""
    db_session.autoflush = False
    first_day = date(2026, 9, 6)
    _run_extra(
        db_session,
        marix_line_company,
        _list_html([], [_EXTRA_UP_0907]),
        {EXTRA_UP_0907: "extra_up_20260907.html"},
        first_day,
        datetime(2026, 9, 6, 6, 0),
    )
    _null_departure_times(db_session)
    assert _up_cross(db_session)
    _run_extra(
        db_session,
        marix_line_company,
        _list_html([], []),
        {},
        first_day,
        datetime(2026, 9, 6, 6, 30),
    )
    assert _up_cross(db_session) == []


@resp_mock.activate
def test_vanished_extra_without_times_is_kept_when_date_is_today(
    db_session, marix_line_company
):
    """時刻が NULL で出港日が今日なら、出港済みかもしれないので残す。"""
    db_session.autoflush = False
    _run_extra(
        db_session,
        marix_line_company,
        _list_html([], [_EXTRA_UP_0907]),
        {EXTRA_UP_0907: "extra_up_20260907.html"},
        _DAY_0907,
        datetime(2026, 9, 7, 6, 0),
    )
    _null_departure_times(db_session)
    kept = _up_cross(db_session)
    _run_extra(
        db_session,
        marix_line_company,
        _list_html([], []),
        {},
        _DAY_0907,
        datetime(2026, 9, 7, 6, 30),
    )
    assert _up_cross(db_session) == kept


# ---------------------------------------------------------------------------
# PR #93 レビュー
# ---------------------------------------------------------------------------


def _naze_extra_list(down: bool) -> str:
    voyage = ("temporary alert", EXTRA_UP_0927, _INFO2_NAZE_0927)
    return _list_html([voyage], []) if down else _list_html([], [voyage])


def _rows_of_url(db_session, url):
    return [
        (r.route_id, r.status)
        for r in db_session.query(DepartureStatus).filter_by(source_url=url)
    ]


@resp_mock.activate
def test_extra_voyage_rows_move_when_direction_changes(db_session, marix_line_company):
    """臨時便の方向が前の回と変わったら、前の航路の行は消える（ルール6は航路で絞らない）。"""
    db_session.autoflush = False
    pages = {EXTRA_UP_0927: "extra_up_naze_20260927.html"}
    down, up = _routes(db_session, marix_line_company)
    _run_extra(db_session, marix_line_company, _naze_extra_list(True), pages, _DAY_0927)
    assert set(_rows_of_url(db_session, EXTRA_UP_0927)) == {(down.id, "extra")}

    _run_extra(
        db_session, marix_line_company, _naze_extra_list(False), pages, _DAY_0927
    )
    assert _rows_of_url(db_session, EXTRA_UP_0927) == [(up.id, "extra")]


def _copy_row(db_session, row, **kw):
    values = {c.name: getattr(row, c.name) for c in DepartureStatus.__table__.columns}
    values.pop("id")
    values.update(kw)
    db_session.add(DepartureStatus(**values))
    db_session.commit()


@resp_mock.activate
def test_vanished_extra_rows_removed_on_both_routes(db_session, marix_line_company):
    """取りやめた臨時便の extra の行は、下り・上りのどちらにあっても消える。"""
    db_session.autoflush = False
    pages = {EXTRA_UP_0927: "extra_up_naze_20260927.html"}
    _run_extra(
        db_session, marix_line_company, _naze_extra_list(False), pages, _DAY_0927
    )
    down, up = _routes(db_session, marix_line_company)
    (row,) = db_session.query(DepartureStatus).filter_by(source_url=EXTRA_UP_0927)
    _copy_row(db_session, row, route_id=down.id)

    _run_extra(db_session, marix_line_company, _list_html([], []), {}, _DAY_0927)
    assert _rows_of_url(db_session, EXTRA_UP_0927) == []


@resp_mock.activate
def test_vanished_extra_keeps_rows_of_other_statuses(db_session, marix_line_company):
    """取りやめで消すのは extra の行だけ。出港済みかを見ていない予備ルートの行などは残す。"""
    db_session.autoflush = False
    pages = {EXTRA_UP_0927: "extra_up_naze_20260927.html"}
    _run_extra(
        db_session, marix_line_company, _naze_extra_list(False), pages, _DAY_0927
    )
    _, up = _routes(db_session, marix_line_company)
    (row,) = db_session.query(DepartureStatus).filter_by(source_url=EXTRA_UP_0927)
    naha = db_session.query(Port).filter_by(name="那覇").one()
    _copy_row(
        db_session,
        row,
        port_id=naha.id,
        ship_name="",
        status="operating",
        scheduled_departure_at=None,
    )

    _run_extra(db_session, marix_line_company, _list_html([], []), {}, _DAY_0927)
    assert _rows_of_url(db_session, EXTRA_UP_0927) == [(up.id, "operating")]


@resp_mock.activate
def test_voyage_kind_warns_when_url_was_not_fetched(db_session, marix_line_company):
    """fetch() で取っていない URL は定期便として扱い、warning を出す。"""
    from bs4 import BeautifulSoup

    setup_port_master(db_session, marix_line_company)
    _mock_extra_pages(_list_html([], []), {})
    scraper = MarixLine(db_session, marix_line_company.id)
    scraper.fetch()
    block = BeautifulSoup(
        _list_html([("route alert", DOWN_0906, _INFO2_DOWN_0906)], []), "lxml"
    ).select_one("div.status_single_cover")
    with structlog.testing.capture_logs() as logs:
        assert scraper._voyage_kind(block, DOWN_0906) == "regular"
    assert "voyage_kind_not_fetched" in {log["event"] for log in logs}
