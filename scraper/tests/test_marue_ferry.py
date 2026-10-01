"""
MarueFerry スクレイパーのユニットテスト。

便検索・鹿児島航路ページ・船別詳細ページは、実サイトから保存した fixture（tests/fixtures/marue/）を
もとにしたHTMLを responses でモックする。
DBは SQLite in-memory を使用（conftest.py の db_session / marue_ferry_company フィクスチャ）。
"""
import re
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs

import pytest
import responses as resp_mock
import structlog
from sqlalchemy import select

from scraper.db.models import DepartureStatus, OperationStatusEnum, Route
from scraper.scrapers.marue_ferry import KAGOSHIMA_URL, SEARCH_URL, MarueFerry
from tests.conftest import read_fixture, setup_port_master

NOW = datetime(2026, 10, 1, 12, 0)

# 港コード
KAGOSHIMA, NAZE, KAMETOKU, WADOMARI, YORON, MOTOBU, NAHA = "50", "70", "78", "80", "82", "84", "83"


# ---------------------------------------------------------------------------
# 時刻・HTTP のモック
# ---------------------------------------------------------------------------

@contextmanager
def fixed_now(now: datetime = NOW):
    """marue_ferry と base の date.today() / datetime.now() を固定する。"""

    class _Date(date):
        @classmethod
        def today(cls):
            return now.date()

    class _DateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    with patch("scraper.scrapers.marue_ferry.date", _Date), \
            patch("scraper.scrapers.marue_ferry.datetime", _DateTime), \
            patch("scraper.scrapers.base.datetime", _DateTime):
        yield


@pytest.fixture(autouse=True)
def no_sleep():
    with patch("scraper.scrapers.marue_ferry.time.sleep") as sleep:
        yield sleep


def search_html(rows: list[tuple[str, str, str, str]] | None) -> str:
    """実際の検索結果ページの tbody を差し替える。rows は (船名, 乗船日時, 下船日時, 会社名)。None ならテーブルごと消す。"""
    base = read_fixture("marue/search_ship.html")
    if rows is None:
        return re.sub(r'<table class="s-result".*?</table>', "", base, flags=re.S)
    trs = "".join(
        f'<tr><td><a href="../kagoshima">鹿児島航路</a></td><td>{ship}</td><td>{dep}</td>'
        f"<td>{arr}</td><td>735km</td><td>{company}</td><td></td></tr>"
        for ship, dep, arr, company in rows
    )
    return re.sub(r"(<tbody>).*?(</tbody>)", rf"\g<1>{trs}\g<2>", base, flags=re.S)


def marue(ship, dep, arr):
    return (ship, dep, arr, "マルエーフェリー")


OTHER = ("※下記参照", "－", "－", "マリックスライン㈱")


def mock_search(results: dict[tuple[str, str, str], str], default: str | None = None):
    """POST の (startPort, endPort, startDate) で返す HTML を決める。無いキーは default（既定は0件）。"""
    default = default if default is not None else read_fixture("marue/search_empty.html")

    def callback(request):
        q = parse_qs(request.body)
        key = (q["startPort"][0], q["endPort"][0], q["startDate"][0])
        return 200, {}, results.get(key, default)

    resp_mock.add_callback(resp_mock.POST, SEARCH_URL, callback=callback)


def mock_kagoshima(html: str | None = None):
    resp_mock.add(resp_mock.GET, KAGOSHIMA_URL, body=html or read_fixture("marue/kagoshima.html"), status=200)
    detail = read_fixture("marue/ship_detail_normal.html")
    resp_mock.add(resp_mock.GET, "https://www.aline-ferry.com/status/route-kagoshima/ferry-akebono/21525/", body=detail)
    resp_mock.add(resp_mock.GET, "https://www.aline-ferry.com/status/route-kagoshima/ferry-naminoue/14640/", body=detail)


def search_calls():
    """便検索の呼び出し（startPort, endPort, startDate）の一覧。"""
    result = []
    for call in resp_mock.calls:
        if call.request.method == "POST":
            q = parse_qs(call.request.body)
            result.append((q["startPort"][0], q["endPort"][0], q["startDate"][0]))
    return result


def run_scraper(db_session, company_id):
    scraper = MarueFerry(db_session, company_id)
    with fixed_now():
        records = scraper.parse(scraper.fetch())
        departures = scraper.parse_departures()
    return scraper, records, departures


def routes_of(db_session, company):
    routes = db_session.execute(select(Route).where(Route.ferry_company_id == company.id)).scalars().all()
    return next(r for r in routes if r.origin_port == "鹿児島"), next(r for r in routes if r.origin_port == "那覇")


def find(departures, route, port, d, ship=None):
    rows = [
        r for r in departures
        if r["route_id"] == route.id and r["port_id"] == port.id and r["departure_date"] == d
        and (ship is None or r["ship_name"] == ship)
    ]
    assert len(rows) == 1, rows
    return rows[0]


D1001 = "2026年10月01日"
D1002 = "2026年10月02日"
D1004 = "2026年10月04日"


def kagoshima_html(akebono=("通常運航", "通常運航致しております。"), naminoue=("通常運航", "通常運航致しております。")):
    """実際の鹿児島航路ページの船ブロックのタグと抜粋を差し替える。"""
    html = read_fixture("marue/kagoshima.html")
    for ship, (tag, excerpt) in (("フェリーあけぼの", akebono), ("フェリー波之上", naminoue)):
        pattern = rf'({re.escape(ship)}</div>.*?<div class="tag-list">\s*<span[^>]*>)[^<]*(</span>.*?<div class="situation-excerpt">)(.*?)(</div>)'
        html, n = re.subn(pattern, rf"\g<1>{tag}\g<2>{excerpt}\g<4>", html, count=1, flags=re.S)
        assert n == 1, ship
    return html


# 今日：下りは波之上（マルエー）、上りはマリックス
TODAY_SEARCHES = {
    (KAGOSHIMA, NAHA, D1001): search_html([marue("フェリー波之上", "2026年10月1日 18:00", "2026年10月2日 19:00")]),
    (NAHA, KAGOSHIMA, D1001): search_html([OTHER]),
}


@pytest.fixture
def marue_with_ports(db_session, marue_ferry_company, marix_line_company):
    ports = setup_port_master(db_session, marue_ferry_company, marix_line_company)
    return marue_ferry_company, ports


# ---------------------------------------------------------------------------
# 便検索
# ---------------------------------------------------------------------------

def test_format_search_date():
    assert MarueFerry._format_search_date(date(2026, 10, 4)) == "2026年10月04日"
    assert MarueFerry._format_search_date(date(2026, 1, 9)) == "2026年01月09日"


@resp_mock.activate
def test_search_posts_japanese_date_format(db_session, marue_with_ports):
    company, _ = marue_with_ports
    mock_search(TODAY_SEARCHES)
    mock_kagoshima()

    run_scraper(db_session, company.id)

    calls = search_calls()
    assert (KAGOSHIMA, NAHA, D1001) in calls
    assert (NAHA, KAGOSHIMA, D1001) in calls
    assert all(re.fullmatch(r"\d{4}年\d{2}月\d{2}日", c[2]) for c in calls)
    # 今日〜3日先 × 方向2 × 出発港6（行が無いので2日先以降も検索する）
    assert len(calls) == 48
    # 終点は出発港として検索しない
    assert (NAHA, NAHA, D1001) not in calls and (KAGOSHIMA, KAGOSHIMA, D1001) not in calls


@resp_mock.activate
def test_search_parses_real_result(db_session, marue_with_ports):
    company, _ = marue_with_ports
    mock_search({(NAZE, NAHA, D1004): read_fixture("marue/search_ship.html")})
    scraper = MarueFerry(db_session, company.id)
    rows = scraper._search(NAZE, NAHA, date(2026, 10, 4))
    assert len(rows) == 1
    row = rows[0]
    assert row.ship_name == "フェリーあけぼの"
    assert row.company_name == "マルエーフェリー"
    assert row.is_other_company is False
    assert row.departure_at == datetime(2026, 10, 4, 5, 50)
    assert row.arrival_at == datetime(2026, 10, 4, 19, 0)


@resp_mock.activate
def test_search_other_company_and_empty(db_session, marue_with_ports):
    company, _ = marue_with_ports
    mock_search({
        (NAZE, NAHA, D1001): read_fixture("marue/search_other_company.html"),
        (NAZE, NAHA, D1002): read_fixture("marue/search_empty.html"),
    })
    scraper = MarueFerry(db_session, company.id)
    other = scraper._search(NAZE, NAHA, date(2026, 10, 1))
    assert len(other) == 1 and other[0].is_other_company and other[0].departure_at is None
    assert scraper._search(NAZE, NAHA, date(2026, 10, 2)) == []


@resp_mock.activate
def test_search_without_table_is_failure(db_session, marue_with_ports):
    company, _ = marue_with_ports
    mock_search({}, default=search_html(None))
    scraper = MarueFerry(db_session, company.id)
    with structlog.testing.capture_logs() as logs:
        assert scraper._search(NAZE, NAHA, date(2026, 10, 1)) is None
    assert any(log["event"] == "result_table_missing" for log in logs)


@resp_mock.activate
def test_sleep_between_searches(db_session, marue_with_ports, no_sleep):
    company, _ = marue_with_ports
    mock_search(TODAY_SEARCHES)
    mock_kagoshima()

    run_scraper(db_session, company.id)

    assert no_sleep.call_count == len(search_calls()) - 1
    no_sleep.assert_called_with(0.5)


@resp_mock.activate
def test_far_searches_are_decided_per_key(db_session, marue_with_ports):
    """2〜3日先は、checked_at が6時間以内のキーは検索せず、行が無いキーと古いキーは検索する。"""
    company, ports = marue_with_ports
    down, _ = routes_of(db_session, company)
    day2 = date(2026, 10, 3)
    # 鹿児島発 10/3：1時間前に確認済み → 検索しない
    # 名瀬発 10/3：7時間前 → 検索する
    for port, hours in ((ports["鹿児島"], 1), (ports["名瀬"], 7)):
        db_session.add(DepartureStatus(
            route_id=down.id, port_id=port.id, departure_date=day2, ship_name="",
            status="no_service", content_hash="x" * 64,
            scraped_at=NOW - timedelta(hours=hours), checked_at=NOW - timedelta(hours=hours),
        ))
    db_session.commit()
    mock_search(TODAY_SEARCHES)
    mock_kagoshima()

    run_scraper(db_session, company.id)

    calls = search_calls()
    assert (KAGOSHIMA, NAHA, "2026年10月03日") not in calls
    assert (NAZE, NAHA, "2026年10月03日") in calls
    assert (KAMETOKU, NAHA, "2026年10月03日") in calls  # 行が無い
    assert len(calls) == 47
    # 今日・明日は行があっても毎回検索する
    assert (KAGOSHIMA, NAHA, D1002) in calls


@resp_mock.activate
def test_failed_far_key_is_retried_next_run(db_session, marue_with_ports):
    """一部のキーだけ失敗した次の実行で、失敗したキーだけ取り直す。"""
    company, _ = marue_with_ports
    broken = search_html(None)
    mock_search({**TODAY_SEARCHES, (NAZE, NAHA, "2026年10月03日"): broken})
    mock_kagoshima()
    scraper, _, departures = run_scraper(db_session, company.id)
    with fixed_now():
        scraper._upsert_departures(departures)
    db_session.commit()

    resp_mock.calls.reset()
    run_scraper(db_session, company.id)

    far = [c for c in search_calls() if c[2] in ("2026年10月03日", "2026年10月04日")]
    assert far == [(NAZE, NAHA, "2026年10月03日")]


# ---------------------------------------------------------------------------
# 航路単位（parse）
# ---------------------------------------------------------------------------

@resp_mock.activate
def test_route_status_is_decided_per_direction(db_session, marue_with_ports):
    """下りはマルエー運航 → 船ステータス、上りは他社運航 → no_service（research R10）。"""
    company, _ = marue_with_ports
    mock_search(TODAY_SEARCHES)
    mock_kagoshima(kagoshima_html(naminoue=("条件付運航", "気象荒天のため条件付き運航。")))

    _, records, _ = run_scraper(db_session, company.id)

    down, up = routes_of(db_session, company)
    by_route = {r["route_id"]: r for r in records}
    assert by_route[down.id]["status"] == OperationStatusEnum.delayed
    assert by_route[down.id]["status_detail"] == "気象荒天のため条件付き運航。"
    assert by_route[up.id]["status"] == OperationStatusEnum.no_service
    assert by_route[up.id]["status_detail"] is None
    assert all(r["valid_date"] == date(2026, 10, 1) for r in records)


@resp_mock.activate
def test_route_status_both_directions_operating(db_session, marue_with_ports):
    company, _ = marue_with_ports
    mock_search({
        (KAGOSHIMA, NAHA, D1001): read_fixture("marue/search_down_1001.html"),
        (NAHA, KAGOSHIMA, D1001): read_fixture("marue/search_up_1001.html"),
    })
    mock_kagoshima(kagoshima_html(akebono=("欠航", "台風接近のため欠航いたします。")))

    _, records, _ = run_scraper(db_session, company.id)

    down, up = routes_of(db_session, company)
    by_route = {r["route_id"]: r for r in records}
    # 下りは波之上（通常運航）、上りはあけぼの（欠航）。他方向の船は混ざらない（US4 シナリオ1）
    assert by_route[down.id]["status"] == OperationStatusEnum.operating
    assert by_route[down.id]["status_detail"] is None
    assert by_route[up.id]["status"] == OperationStatusEnum.cancelled
    assert by_route[up.id]["status_detail"] == "台風接近のため欠航いたします。"


@resp_mock.activate
def test_route_status_no_service_when_empty(db_session, marue_with_ports):
    company, _ = marue_with_ports
    mock_search({})
    mock_kagoshima()

    _, records, _ = run_scraper(db_session, company.id)

    assert len(records) == 2
    assert all(r["status"] == OperationStatusEnum.no_service for r in records)


@resp_mock.activate
def test_route_status_falls_back_to_worst_when_search_fails(db_session, marue_with_ports):
    """検索に失敗したら、船ステータスのうち一番重いもの（安全側）。"""
    company, _ = marue_with_ports
    mock_search({}, default=search_html(None))
    mock_kagoshima(kagoshima_html(naminoue=("欠航", "台風接近のため欠航いたします。")))

    with structlog.testing.capture_logs() as logs:
        _, records, departures = run_scraper(db_session, company.id)

    assert all(r["status"] == OperationStatusEnum.cancelled for r in records)
    assert all(r["status_detail"] == "台風接近のため欠航いたします。" for r in records)
    assert departures == []  # 失敗したキーは港別の行を作らない
    assert any(log["event"] == "origin_search_unavailable" for log in logs)


@resp_mock.activate
def test_route_status_unknown_when_ship_not_in_blocks(db_session, marue_with_ports):
    company, _ = marue_with_ports
    mock_search({(KAGOSHIMA, NAHA, D1001): search_html([marue("フェリー新造船", "2026年10月1日 18:00", "2026年10月2日 19:00")])})
    mock_kagoshima()

    _, records, _ = run_scraper(db_session, company.id)

    down, _ = routes_of(db_session, company)
    assert next(r for r in records if r["route_id"] == down.id)["status"] == OperationStatusEnum.unknown


@resp_mock.activate
def test_parse_raises_when_no_ferry_blocks(db_session, marue_with_ports):
    """マルエーの便があるのに船ブロックが1つも取れない → サイト構造の変更として RuntimeError。"""
    company, _ = marue_with_ports
    mock_search(TODAY_SEARCHES)
    mock_kagoshima("<html><body><p>現在、航路情報はありません。</p></body></html>")

    scraper = MarueFerry(db_session, company.id)
    with fixed_now(), pytest.raises(RuntimeError, match="no ship statuses parsed"):
        scraper.parse(scraper.fetch())


@resp_mock.activate
def test_raw_html_changes_when_origin_search_changes(db_session, marue_with_ports):
    company, _ = marue_with_ports
    mock_search(TODAY_SEARCHES)
    mock_kagoshima()
    scraper = MarueFerry(db_session, company.id)
    with fixed_now():
        html1 = scraper.fetch()

    resp_mock.reset()
    mock_search({})
    mock_kagoshima()
    with fixed_now():
        html2 = scraper.fetch()

    assert html1 != html2


# ---------------------------------------------------------------------------
# 港別（parse_departures）
# ---------------------------------------------------------------------------

@resp_mock.activate
def test_departure_with_ship_gets_ship_status(db_session, marue_with_ports):
    """船名あり → その船の船ステータス（US4 シナリオ1・8）。"""
    company, ports = marue_with_ports
    mock_search({(NAZE, NAHA, D1004): read_fixture("marue/search_ship.html")})
    mock_kagoshima(kagoshima_html(akebono=("条件付運航", "気象荒天のため条件付き運航。")))

    _, _, departures = run_scraper(db_session, company.id)

    down, _ = routes_of(db_session, company)
    row = find(departures, down, ports["名瀬"], date(2026, 10, 4))
    assert row["ship_name"] == "フェリーあけぼの"
    assert row["status"] == OperationStatusEnum.delayed
    assert row["status_detail"] == "気象荒天のため条件付き運航。"
    assert row["scheduled_departure_at"] == datetime(2026, 10, 4, 5, 50)
    assert row["scheduled_arrival_at"] == datetime(2026, 10, 4, 19, 0)
    assert row["operated_by_company_id"] is None


@resp_mock.activate
def test_departure_other_company_is_no_service_with_operator(db_session, marue_with_ports, marix_line_company):
    """他社運航 → no_service + operated_by = マリックスライン（US4 シナリオ7）。"""
    company, ports = marue_with_ports
    mock_search({(NAZE, NAHA, D1001): read_fixture("marue/search_other_company.html")})
    mock_kagoshima()

    _, _, departures = run_scraper(db_session, company.id)

    down, _ = routes_of(db_session, company)
    row = find(departures, down, ports["名瀬"], date(2026, 10, 1))
    assert row["status"] == OperationStatusEnum.no_service
    assert row["ship_name"] == ""
    assert row["operated_by_company_id"] == marix_line_company.id


@resp_mock.activate
def test_departure_empty_is_no_service(db_session, marue_with_ports):
    company, ports = marue_with_ports
    mock_search({})
    mock_kagoshima()

    _, _, departures = run_scraper(db_session, company.id)

    _, up = routes_of(db_session, company)
    row = find(departures, up, ports["那覇"], date(2026, 10, 2))
    assert row["status"] == OperationStatusEnum.no_service
    assert row["operated_by_company_id"] is None
    # 方向2 × 出発港6 × 4日
    assert len(departures) == 48


@resp_mock.activate
def test_departure_unknown_ship_is_unknown_with_warning(db_session, marue_with_ports):
    """船名が船ブロックに無い → unknown + warning（US4 シナリオ6）。"""
    company, ports = marue_with_ports
    mock_search({(NAZE, NAHA, D1004): search_html([marue("フェリー新造船", "2026年10月4日 05:50", "2026年10月4日 19:00")])})
    mock_kagoshima()

    with structlog.testing.capture_logs() as logs:
        _, _, departures = run_scraper(db_session, company.id)

    down, _ = routes_of(db_session, company)
    assert find(departures, down, ports["名瀬"], date(2026, 10, 4))["status"] == OperationStatusEnum.unknown
    assert any(log["event"] == "ship_not_found" and log["ship"] == "フェリー新造船" for log in logs)


@resp_mock.activate
def test_later_voyage_of_same_ship_is_scheduled(db_session, marue_with_ports):
    """同じ船の2便目以降 → status None（運航予定、FR-021）。"""
    company, ports = marue_with_ports
    mock_search({
        # あけぼの：今日 那覇発の上り（明日着）と、10/4 名瀬発の下り
        (NAHA, KAGOSHIMA, D1001): read_fixture("marue/search_up_1001.html"),
        (NAZE, NAHA, D1004): read_fixture("marue/search_ship.html"),
    })
    mock_kagoshima(kagoshima_html(akebono=("欠航", "台風接近のため欠航いたします。")))

    _, _, departures = run_scraper(db_session, company.id)

    down, up = routes_of(db_session, company)
    assert find(departures, up, ports["那覇"], date(2026, 10, 1))["status"] == OperationStatusEnum.cancelled
    later = find(departures, down, ports["名瀬"], date(2026, 10, 4))
    assert later["status"] is None
    assert later["status_detail"] is None


@resp_mock.activate
def test_same_voyage_at_all_ports_gets_ship_status(db_session, marue_with_ports):
    """同じ便（下船日時が同じ）なら、どの出発港の行にも船ステータスが入る。"""
    company, ports = marue_with_ports
    arr = "2026年10月2日 19:00"
    mock_search({
        (KAGOSHIMA, NAHA, D1001): search_html([marue("フェリー波之上", "2026年10月1日 18:00", arr)]),
        (NAZE, NAHA, D1002): search_html([marue("フェリー波之上", "2026年10月2日 05:50", arr)]),
        (MOTOBU, NAHA, D1002): search_html([marue("フェリー波之上", "2026年10月2日 17:10", arr)]),
    })
    mock_kagoshima(kagoshima_html(naminoue=("欠航", "台風接近のため欠航いたします。")))

    _, _, departures = run_scraper(db_session, company.id)

    down, _ = routes_of(db_session, company)
    for port, d in ((ports["鹿児島"], date(2026, 10, 1)), (ports["名瀬"], date(2026, 10, 2)), (ports["本部"], date(2026, 10, 2))):
        assert find(departures, down, port, d)["status"] == OperationStatusEnum.cancelled


@resp_mock.activate
def test_departures_have_freeze_and_replace_scope(db_session, marue_with_ports):
    company, ports = marue_with_ports
    mock_search(TODAY_SEARCHES)
    mock_kagoshima()

    _, _, departures = run_scraper(db_session, company.id)

    assert departures
    for r in departures:
        assert r["freeze_after_departure"] is True
        assert r["replace_scope"] == (r["route_id"], r["port_id"], r["departure_date"])
        assert r["source_url"] == SEARCH_URL


@resp_mock.activate
def test_run_writes_route_and_departures(db_session, marue_with_ports):
    company, _ = marue_with_ports
    mock_search(TODAY_SEARCHES)
    mock_kagoshima()

    scraper = MarueFerry(db_session, company.id)
    with fixed_now():
        scraper.run()
    db_session.commit()

    rows = db_session.execute(select(DepartureStatus)).scalars().all()
    assert len(rows) == 48
    assert all(r.checked_at == NOW for r in rows)
