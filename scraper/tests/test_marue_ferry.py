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
KAGOSHIMA, NAZE, KAMETOKU, WADOMARI, YORON, MOTOBU, NAHA = (
    "50",
    "70",
    "78",
    "80",
    "82",
    "84",
    "83",
)


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

    with (
        patch("scraper.scrapers.marue_ferry.date", _Date),
        patch("scraper.scrapers.marue_ferry.datetime", _DateTime),
        patch("scraper.scrapers.base.datetime", _DateTime),
    ):
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
    default = (
        default if default is not None else read_fixture("marue/search_empty.html")
    )

    def callback(request):
        q = parse_qs(request.body)
        key = (q["startPort"][0], q["endPort"][0], q["startDate"][0])
        return 200, {}, results.get(key, default)

    resp_mock.add_callback(resp_mock.POST, SEARCH_URL, callback=callback)


def mock_kagoshima(html: str | None = None):
    resp_mock.add(
        resp_mock.GET,
        KAGOSHIMA_URL,
        body=html or read_fixture("marue/kagoshima.html"),
        status=200,
    )
    detail = read_fixture("marue/ship_detail_normal.html")
    resp_mock.add(
        resp_mock.GET,
        "https://www.aline-ferry.com/status/route-kagoshima/ferry-akebono/21525/",
        body=detail,
    )
    resp_mock.add(
        resp_mock.GET,
        "https://www.aline-ferry.com/status/route-kagoshima/ferry-naminoue/14640/",
        body=detail,
    )


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
    routes = (
        db_session.execute(select(Route).where(Route.ferry_company_id == company.id))
        .scalars()
        .all()
    )
    return next(r for r in routes if r.origin_port == "鹿児島"), next(
        r for r in routes if r.origin_port == "那覇"
    )


def find(departures, route, port, d, ship=None):
    rows = [
        r
        for r in departures
        if r["route_id"] == route.id
        and r["port_id"] == port.id
        and r["departure_date"] == d
        and (ship is None or r["ship_name"] == ship)
    ]
    assert len(rows) == 1, rows
    return rows[0]


D1001 = "2026年10月01日"
D1002 = "2026年10月02日"
D1004 = "2026年10月04日"


def kagoshima_html(
    akebono=("通常運航", "通常運航致しております。"),
    naminoue=("通常運航", "通常運航致しております。"),
):
    """実際の鹿児島航路ページの船ブロックのタグと抜粋を差し替える。"""
    html = read_fixture("marue/kagoshima.html")
    for ship, (tag, excerpt) in (
        ("フェリーあけぼの", akebono),
        ("フェリー波之上", naminoue),
    ):
        pattern = rf'({re.escape(ship)}</div>.*?<div class="tag-list">\s*<span[^>]*>)[^<]*(</span>.*?<div class="situation-excerpt">)(.*?)(</div>)'
        html, n = re.subn(
            pattern, rf"\g<1>{tag}\g<2>{excerpt}\g<4>", html, count=1, flags=re.S
        )
        assert n == 1, ship
    return html


# 今日：下りは波之上（マルエー）、上りはマリックス
TODAY_SEARCHES = {
    (KAGOSHIMA, NAHA, D1001): search_html(
        [marue("フェリー波之上", "2026年10月1日 18:00", "2026年10月2日 19:00")]
    ),
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
    assert (NAHA, NAHA, D1001) not in calls and (
        KAGOSHIMA,
        KAGOSHIMA,
        D1001,
    ) not in calls


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
    mock_search(
        {
            (NAZE, NAHA, D1001): read_fixture("marue/search_other_company.html"),
            (NAZE, NAHA, D1002): read_fixture("marue/search_empty.html"),
        }
    )
    scraper = MarueFerry(db_session, company.id)
    other = scraper._search(NAZE, NAHA, date(2026, 10, 1))
    assert (
        len(other) == 1 and other[0].is_other_company and other[0].departure_at is None
    )
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
        db_session.add(
            DepartureStatus(
                route_id=down.id,
                port_id=port.id,
                departure_date=day2,
                ship_name="",
                status="no_service",
                content_hash="x" * 64,
                scraped_at=NOW - timedelta(hours=hours),
                checked_at=NOW - timedelta(hours=hours),
            )
        )
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
    mock_kagoshima(
        kagoshima_html(naminoue=("条件付運航", "気象荒天のため条件付き運航。"))
    )

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
    mock_search(
        {
            (KAGOSHIMA, NAHA, D1001): read_fixture("marue/search_down_1001.html"),
            (NAHA, KAGOSHIMA, D1001): read_fixture("marue/search_up_1001.html"),
        }
    )
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
def test_route_status_falls_back_to_worst_when_search_fails(
    db_session, marue_with_ports
):
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
    mock_search(
        {
            (KAGOSHIMA, NAHA, D1001): search_html(
                [marue("フェリー新造船", "2026年10月1日 18:00", "2026年10月2日 19:00")]
            )
        }
    )
    mock_kagoshima()

    _, records, _ = run_scraper(db_session, company.id)

    down, _ = routes_of(db_session, company)
    assert (
        next(r for r in records if r["route_id"] == down.id)["status"]
        == OperationStatusEnum.unknown
    )


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


@resp_mock.activate
def test_raw_html_changes_when_today_origin_voyage_departs(
    db_session, marue_with_ports
):
    """PR #86 中：HTML も検索結果も同じまま出港時刻（18:00）をまたいだら hash を変えて、航路単位も更新する。"""
    company, _ = marue_with_ports
    mock_search(TODAY_SEARCHES)
    mock_kagoshima()
    scraper = MarueFerry(db_session, company.id)
    with fixed_now(datetime(2026, 10, 1, 12, 0)):
        before = scraper.fetch()
    with fixed_now(datetime(2026, 10, 1, 12, 15)):
        same = scraper.fetch()
    with fixed_now(datetime(2026, 10, 1, 18, 5)):
        after = scraper.fetch()

    assert before == same
    assert before != after


# ---------------------------------------------------------------------------
# 港別（parse_departures）
# ---------------------------------------------------------------------------


@resp_mock.activate
def test_departure_with_ship_gets_ship_status(db_session, marue_with_ports):
    """船名あり → その船の船ステータス（US4 シナリオ1・8）。"""
    company, ports = marue_with_ports
    mock_search({(NAZE, NAHA, D1004): read_fixture("marue/search_ship.html")})
    mock_kagoshima(
        kagoshima_html(akebono=("条件付運航", "気象荒天のため条件付き運航。"))
    )

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
def test_departure_other_company_is_no_service_with_operator(
    db_session, marue_with_ports, marix_line_company
):
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
    mock_search(
        {
            (NAZE, NAHA, D1004): search_html(
                [marue("フェリー新造船", "2026年10月4日 05:50", "2026年10月4日 19:00")]
            )
        }
    )
    mock_kagoshima()

    with structlog.testing.capture_logs() as logs:
        _, _, departures = run_scraper(db_session, company.id)

    down, _ = routes_of(db_session, company)
    assert (
        find(departures, down, ports["名瀬"], date(2026, 10, 4))["status"]
        == OperationStatusEnum.unknown
    )
    assert any(
        log["event"] == "ship_not_found" and log["ship"] == "フェリー新造船"
        for log in logs
    )


@resp_mock.activate
def test_later_voyage_of_same_ship_is_scheduled(db_session, marue_with_ports):
    """同じ船の2便目以降 → status None（運航予定、FR-021）。"""
    company, ports = marue_with_ports
    mock_search(
        {
            # あけぼの：今日 那覇発の上り（明日着）と、10/4 名瀬発の下り
            (NAHA, KAGOSHIMA, D1001): read_fixture("marue/search_up_1001.html"),
            (NAZE, NAHA, D1004): read_fixture("marue/search_ship.html"),
        }
    )
    mock_kagoshima(kagoshima_html(akebono=("欠航", "台風接近のため欠航いたします。")))

    _, _, departures = run_scraper(db_session, company.id)

    down, up = routes_of(db_session, company)
    assert (
        find(departures, up, ports["那覇"], date(2026, 10, 1))["status"]
        == OperationStatusEnum.cancelled
    )
    later = find(departures, down, ports["名瀬"], date(2026, 10, 4))
    assert later["status"] is None
    assert later["status_detail"] is None


@resp_mock.activate
def test_same_voyage_at_all_ports_gets_ship_status(db_session, marue_with_ports):
    """同じ便（下船日時が同じ）なら、どの出発港の行にも船ステータスが入る。"""
    company, ports = marue_with_ports
    arr = "2026年10月2日 19:00"
    mock_search(
        {
            (KAGOSHIMA, NAHA, D1001): search_html(
                [marue("フェリー波之上", "2026年10月1日 18:00", arr)]
            ),
            (NAZE, NAHA, D1002): search_html(
                [marue("フェリー波之上", "2026年10月2日 05:50", arr)]
            ),
            (MOTOBU, NAHA, D1002): search_html(
                [marue("フェリー波之上", "2026年10月2日 17:10", arr)]
            ),
        }
    )
    mock_kagoshima(kagoshima_html(naminoue=("欠航", "台風接近のため欠航いたします。")))

    _, _, departures = run_scraper(db_session, company.id)

    down, _ = routes_of(db_session, company)
    for port, d in (
        (ports["鹿児島"], date(2026, 10, 1)),
        (ports["名瀬"], date(2026, 10, 2)),
        (ports["本部"], date(2026, 10, 2)),
    ):
        assert (
            find(departures, down, port, d)["status"] == OperationStatusEnum.cancelled
        )


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


# ---------------------------------------------------------------------------
# 港別情報の反映（US3 シナリオ1〜3、US4 シナリオ3〜5）
# ---------------------------------------------------------------------------

DOWN_ARR = "2026年10月2日 19:00"
UP_ARR = "2026年10月2日 08:30"
# あけぼの：10/1 鹿児島発の下り（途中港は 10/2）、波之上：10/1 那覇発の上り
VOYAGE_SEARCHES = {
    (KAGOSHIMA, NAHA, D1001): search_html(
        [marue("フェリーあけぼの", "2026年10月1日 18:00", DOWN_ARR)]
    ),
    (NAZE, NAHA, D1002): search_html(
        [marue("フェリーあけぼの", "2026年10月2日 05:50", DOWN_ARR)]
    ),
    (KAMETOKU, NAHA, D1002): search_html(
        [marue("フェリーあけぼの", "2026年10月2日 09:40", DOWN_ARR)]
    ),
    (WADOMARI, NAHA, D1002): search_html(
        [marue("フェリーあけぼの", "2026年10月2日 12:00", DOWN_ARR)]
    ),
    (YORON, NAHA, D1002): search_html(
        [marue("フェリーあけぼの", "2026年10月2日 14:10", DOWN_ARR)]
    ),
    (MOTOBU, NAHA, D1002): search_html(
        [marue("フェリーあけぼの", "2026年10月2日 17:10", DOWN_ARR)]
    ),
    (NAHA, KAGOSHIMA, D1001): search_html(
        [marue("フェリー波之上", "2026年10月1日 07:00", UP_ARR)]
    ),
    (MOTOBU, KAGOSHIMA, D1001): search_html(
        [marue("フェリー波之上", "2026年10月1日 09:20", UP_ARR)]
    ),
    (YORON, KAGOSHIMA, D1001): search_html(
        [marue("フェリー波之上", "2026年10月1日 12:10", UP_ARR)]
    ),
    (WADOMARI, KAGOSHIMA, D1001): search_html(
        [marue("フェリー波之上", "2026年10月1日 14:40", UP_ARR)]
    ),
    (KAMETOKU, KAGOSHIMA, D1001): search_html(
        [marue("フェリー波之上", "2026年10月1日 17:00", UP_ARR)]
    ),
    (NAZE, KAGOSHIMA, D1001): search_html(
        [marue("フェリー波之上", "2026年10月1日 21:20", UP_ARR)]
    ),
}
DOWN_PORTS = [
    ("鹿児島", date(2026, 10, 1)),
    ("名瀬", date(2026, 10, 2)),
    ("亀徳", date(2026, 10, 2)),
    ("和泊", date(2026, 10, 2)),
    ("与論", date(2026, 10, 2)),
    ("本部", date(2026, 10, 2)),
]
UP_PORTS = ["那覇", "本部", "与論", "和泊", "亀徳", "名瀬"]


def run_with_ships(
    db_session, company, akebono, naminoue=("通常運航", "通常運航致しております。")
):
    mock_search(VOYAGE_SEARCHES)
    mock_kagoshima(kagoshima_html(akebono=akebono, naminoue=naminoue))
    with structlog.testing.capture_logs() as logs:
        _, _, departures = run_scraper(db_session, company.id)
    return departures, logs


def down_statuses(db_session, company, ports, departures):
    down, _ = routes_of(db_session, company)
    return {name: find(departures, down, ports[name], d) for name, d in DOWN_PORTS}


def up_statuses(db_session, company, ports, departures):
    _, up = routes_of(db_session, company)
    return {
        name: find(departures, up, ports[name], date(2026, 10, 1)) for name in UP_PORTS
    }


@resp_mock.activate
def test_conditional_ports_only_are_delayed(db_session, marue_with_ports):
    """条件付の船で和泊・与論の記載 → その方向の和泊・与論だけ delayed、他は operating（US3 シナリオ1・3）。"""
    company, ports = marue_with_ports
    departures, _ = run_with_ships(
        db_session,
        company,
        ("条件付運航", "気象荒天のため。条件付寄港地: 和泊港、与論港"),
    )

    rows = down_statuses(db_session, company, ports, departures)
    assert rows["和泊"]["status"] == OperationStatusEnum.delayed
    assert rows["与論"]["status"] == OperationStatusEnum.delayed
    assert "条件付寄港地" in rows["与論"]["status_detail"]
    for name in ["鹿児島", "名瀬", "亀徳", "本部"]:
        assert rows[name]["status"] == OperationStatusEnum.operating
        assert rows[name]["status_detail"] is None


@resp_mock.activate
def test_conditional_without_ports_is_delayed_everywhere(db_session, marue_with_ports):
    """条件付で港の記載なし → 全港 delayed + port_notice_unmatched（US3 シナリオ2）。"""
    company, ports = marue_with_ports
    departures, logs = run_with_ships(
        db_session, company, ("条件付運航", "気象荒天のため条件付き運航となります。")
    )

    rows = down_statuses(db_session, company, ports, departures)
    assert all(r["status"] == OperationStatusEnum.delayed for r in rows.values())
    assert all(
        r["status_detail"] == "気象荒天のため条件付き運航となります。"
        for r in rows.values()
    )
    unmatched = [log for log in logs if log["event"] == "port_notice_unmatched"]
    assert len(unmatched) == 1 and unmatched[0]["ship"] == "フェリーあけぼの"


@resp_mock.activate
def test_cancelled_ship_ignores_port_notices(db_session, marue_with_ports):
    """欠航の船 → 記載があっても全港 cancelled。"""
    company, ports = marue_with_ports
    departures, _ = run_with_ships(
        db_session, company, ("欠航", "台風接近のため欠航。与論港は条件付寄港。")
    )

    rows = down_statuses(db_session, company, ports, departures)
    assert all(r["status"] == OperationStatusEnum.cancelled for r in rows.values())


@resp_mock.activate
def test_skip_port_is_skipped_only_there(db_session, marue_with_ports):
    """抜港 → その港だけ skipped（欠航ではない）、他は船ステータス（US4 シナリオ3）。"""
    company, ports = marue_with_ports
    departures, _ = run_with_ships(
        db_session, company, ("通常運航", "本日、与論港は抜港となります。")
    )

    rows = down_statuses(db_session, company, ports, departures)
    assert rows["与論"]["status"] == OperationStatusEnum.skipped
    assert "与論港は抜港" in rows["与論"]["status_detail"]
    for name in ["鹿児島", "名瀬", "亀徳", "和泊", "本部"]:
        assert rows[name]["status"] == OperationStatusEnum.operating


@resp_mock.activate
def test_port_change_is_delayed_with_destination(db_session, marue_with_ports):
    """港変更 → delayed、詳細に変更先（US4 シナリオ4）。"""
    company, ports = marue_with_ports
    departures, _ = run_with_ships(
        db_session, company, ("条件付運航", "亀徳港から平土野港へ港変更となります。")
    )

    rows = down_statuses(db_session, company, ports, departures)
    assert rows["亀徳"]["status"] == OperationStatusEnum.delayed
    assert "平土野港" in rows["亀徳"]["status_detail"]
    assert rows["名瀬"]["status"] == OperationStatusEnum.operating


@resp_mock.activate
def test_other_direction_ship_is_not_mixed(db_session, marue_with_ports):
    """下りの船の「与論港は抜港」は、上りの与論発には混ざらない（US4 シナリオ5）。"""
    company, ports = marue_with_ports
    departures, _ = run_with_ships(
        db_session, company, ("通常運航", "与論港は抜港となります。")
    )

    assert (
        down_statuses(db_session, company, ports, departures)["与論"]["status"]
        == OperationStatusEnum.skipped
    )
    up = up_statuses(db_session, company, ports, departures)
    assert all(r["status"] == OperationStatusEnum.operating for r in up.values())
    assert up["与論"]["ship_name"] == "フェリー波之上"


@resp_mock.activate
def test_unmatched_conditional_text_keeps_ship_status(db_session, marue_with_ports):
    """パターンに当てはまらない条件付のテキスト → 船ステータス + port_notice_unmatched。"""
    company, ports = marue_with_ports
    text = "与論港への寄港は天候次第で見合わせる場合があります。"
    departures, logs = run_with_ships(db_session, company, ("条件付運航", text))

    rows = down_statuses(db_session, company, ports, departures)
    assert all(r["status"] == OperationStatusEnum.delayed for r in rows.values())
    assert any(log["event"] == "port_notice_unmatched" for log in logs)


@resp_mock.activate
def test_route_level_parse_is_unchanged_by_port_notices(db_session, marue_with_ports):
    """航路単位の parse は港別情報の影響を受けない（船ステータスのまま）。"""
    company, _ = marue_with_ports
    mock_search(VOYAGE_SEARCHES)
    mock_kagoshima(kagoshima_html(akebono=("通常運航", "与論港は抜港となります。")))

    _, records, _ = run_scraper(db_session, company.id)

    down, _ = routes_of(db_session, company)
    assert (
        next(r for r in records if r["route_id"] == down.id)["status"]
        == OperationStatusEnum.operating
    )


# ---------------------------------------------------------------------------
# 出港済みの行の確定（US4 シナリオ9、FR-020）
# ---------------------------------------------------------------------------

NAZE_0550 = search_html(
    [marue("フェリーあけぼの", "2026年10月1日 05:50", "2026年10月1日 19:00")]
)


def run_at(db_session, company, now, searches, akebono):
    resp_mock.reset()
    mock_search(searches)
    mock_kagoshima(kagoshima_html(akebono=akebono))
    scraper = MarueFerry(db_session, company.id)
    with fixed_now(now):
        scraper.run()
    db_session.commit()


def naze_rows(db_session, company, ports):
    down, _ = routes_of(db_session, company)
    return (
        db_session.execute(
            select(DepartureStatus).where(
                DepartureStatus.route_id == down.id,
                DepartureStatus.port_id == ports["名瀬"].id,
                DepartureStatus.departure_date == date(2026, 10, 1),
            )
        )
        .scalars()
        .all()
    )


@resp_mock.activate
def test_departed_row_is_frozen(db_session, marue_with_ports):
    company, ports = marue_with_ports
    searches = {(NAZE, NAHA, D1001): NAZE_0550}

    # 出港前（05:30）に通常運航で記録
    run_at(
        db_session,
        company,
        datetime(2026, 10, 1, 5, 30),
        searches,
        ("通常運航", "通常運航致しております。"),
    )
    [row] = naze_rows(db_session, company, ports)
    assert row.status == "operating"
    assert row.checked_at == datetime(2026, 10, 1, 5, 30)

    # 20:00 に船ステータスが次の便の「欠航」に変わった
    run_at(
        db_session,
        company,
        datetime(2026, 10, 1, 20, 0),
        searches,
        ("欠航", "台風接近のため欠航いたします。"),
    )
    [row] = naze_rows(db_session, company, ports)
    assert row.status == "operating"
    assert row.checked_at == datetime(2026, 10, 1, 5, 30)
    assert row.scraped_at == datetime(2026, 10, 1, 5, 30)

    # 出港後の検索でその便が返らなくなっても（0件・別の船）、行は消えない
    run_at(
        db_session,
        company,
        datetime(2026, 10, 1, 20, 30),
        {},
        ("通常運航", "通常運航致しております。"),
    )
    run_at(
        db_session,
        company,
        datetime(2026, 10, 1, 21, 0),
        {
            (NAZE, NAHA, D1001): search_html(
                [marue("フェリー波之上", "2026年10月1日 23:00", "2026年10月2日 12:00")]
            ),
        },
        ("通常運航", "通常運航致しております。"),
    )
    akebono = [
        r
        for r in naze_rows(db_session, company, ports)
        if r.ship_name == "フェリーあけぼの"
    ]
    assert len(akebono) == 1
    assert akebono[0].status == "operating"
    assert akebono[0].checked_at == datetime(2026, 10, 1, 5, 30)


@resp_mock.activate
def test_departed_row_is_not_created_on_first_run(db_session, marue_with_ports):
    """DB に行が無い状態で 10:00 に初めて実行 → 05:50 発の行は作らない（港別ページでは「情報なし」）。"""
    company, ports = marue_with_ports
    run_at(
        db_session,
        company,
        datetime(2026, 10, 1, 10, 0),
        {(NAZE, NAHA, D1001): NAZE_0550},
        ("欠航", "台風接近のため欠航いたします。"),
    )

    assert naze_rows(db_session, company, ports) == []


@resp_mock.activate
def test_overnight_voyage_keeps_ship_status_off_next_voyage(
    db_session, marue_with_ports
):
    """日付が変わってから着くまでの上りの便（今日以降の検索に出ない）が走っている間は、
    船ステータスを次の便の行に付けない。"""
    company, ports = marue_with_ports
    _, up = routes_of(db_session, company)
    # 前日の実行で記録した、10/1 21:20 名瀬発 → 10/2 08:30 鹿児島着の波之上
    db_session.add(
        DepartureStatus(
            route_id=up.id,
            port_id=ports["名瀬"].id,
            departure_date=date(2026, 10, 1),
            ship_name="フェリー波之上",
            status="cancelled",
            scheduled_departure_at=datetime(2026, 10, 1, 21, 20),
            scheduled_arrival_at=datetime(2026, 10, 2, 8, 30),
            content_hash="x" * 64,
            scraped_at=datetime(2026, 10, 1, 20, 0),
            checked_at=datetime(2026, 10, 1, 20, 0),
        )
    )
    db_session.commit()
    # 波之上の次の便は 10/3 鹿児島発の下り
    mock_search(
        {
            (KAGOSHIMA, NAHA, "2026年10月03日"): search_html(
                [marue("フェリー波之上", "2026年10月3日 18:00", "2026年10月4日 19:00")]
            ),
        }
    )
    mock_kagoshima(kagoshima_html(naminoue=("欠航", "台風接近のため欠航いたします。")))

    scraper = MarueFerry(db_session, company.id)
    with fixed_now(datetime(2026, 10, 2, 2, 0)):
        scraper.parse(scraper.fetch())
        departures = scraper.parse_departures()

    down, _ = routes_of(db_session, company)
    row = find(departures, down, ports["鹿児島"], date(2026, 10, 3))
    assert row["status"] is None  # 運航予定（走っている便の「欠航」は付けない）


@resp_mock.activate
def test_arrived_recorded_voyage_does_not_block_next_voyage(
    db_session, marue_with_ports
):
    """着いた後の便は候補にならず、次の便に船ステータスが付く。"""
    company, ports = marue_with_ports
    _, up = routes_of(db_session, company)
    db_session.add(
        DepartureStatus(
            route_id=up.id,
            port_id=ports["名瀬"].id,
            departure_date=date(2026, 10, 1),
            ship_name="フェリー波之上",
            status="operating",
            scheduled_departure_at=datetime(2026, 10, 1, 21, 20),
            scheduled_arrival_at=datetime(2026, 10, 2, 8, 30),
            content_hash="x" * 64,
            scraped_at=datetime(2026, 10, 1, 20, 0),
            checked_at=datetime(2026, 10, 1, 20, 0),
        )
    )
    db_session.commit()
    mock_search(
        {
            (KAGOSHIMA, NAHA, "2026年10月03日"): search_html(
                [marue("フェリー波之上", "2026年10月3日 18:00", "2026年10月4日 19:00")]
            ),
        }
    )
    mock_kagoshima(kagoshima_html(naminoue=("欠航", "台風接近のため欠航いたします。")))

    scraper = MarueFerry(db_session, company.id)
    with fixed_now(datetime(2026, 10, 2, 9, 0)):
        scraper.parse(scraper.fetch())
        departures = scraper.parse_departures()

    down, _ = routes_of(db_session, company)
    assert (
        find(departures, down, ports["鹿児島"], date(2026, 10, 3))["status"]
        == OperationStatusEnum.cancelled
    )


@resp_mock.activate
def test_delayed_voyage_uses_searched_arrival_not_frozen_rows(
    db_session, marue_with_ports
):
    """出港済みで確定した行（遅延前の 19:00 着）が残っていても、検索の 21:00 着の便を今の便とする。"""
    company, ports = marue_with_ports
    down, _ = routes_of(db_session, company)
    # 10/1 18:00 鹿児島発（10/2 19:00 着の予定）で記録して出港済み
    db_session.add(
        DepartureStatus(
            route_id=down.id,
            port_id=ports["鹿児島"].id,
            departure_date=date(2026, 10, 1),
            ship_name="フェリー波之上",
            status="operating",
            scheduled_departure_at=datetime(2026, 10, 1, 18, 0),
            scheduled_arrival_at=datetime(2026, 10, 2, 19, 0),
            content_hash="x" * 64,
            scraped_at=datetime(2026, 10, 1, 17, 30),
            checked_at=datetime(2026, 10, 1, 17, 30),
        )
    )
    db_session.commit()
    # 遅延して、途中港以降は 21:00 着になった
    delayed_arr = "2026年10月2日 21:00"
    mock_search(
        {
            (NAZE, "83", D1002): search_html(
                [marue("フェリー波之上", "2026年10月2日 07:50", delayed_arr)]
            ),
            (MOTOBU, "83", D1002): search_html(
                [marue("フェリー波之上", "2026年10月2日 19:10", delayed_arr)]
            ),
        }
    )
    mock_kagoshima(
        kagoshima_html(naminoue=("遅延", "荒天のため約2時間遅れて運航しております。"))
    )

    scraper = MarueFerry(db_session, company.id)
    with fixed_now(datetime(2026, 10, 2, 3, 0)):
        scraper.parse(scraper.fetch())
        departures = scraper.parse_departures()

    for port in ("名瀬", "本部"):
        row = find(departures, down, ports[port], date(2026, 10, 2))
        assert row["status"] == OperationStatusEnum.delayed
        assert row["status_detail"] == "荒天のため約2時間遅れて運航しております。"


@resp_mock.activate
def test_delayed_ship_keeps_delayed_on_unmentioned_ports(db_session, marue_with_ports):
    """船が「遅延」（条件付ではない）で抜港の記載 → 与論だけ抜港、他の港は遅れたまま delayed（FR-006）。"""
    company, ports = marue_with_ports
    departures, logs = run_with_ships(
        db_session,
        company,
        ("遅延", "荒天のため約2時間遅れて運航。与論港は抜港となります。"),
    )

    rows = down_statuses(db_session, company, ports, departures)
    assert rows["与論"]["status"] == OperationStatusEnum.skipped
    for name in ["鹿児島", "名瀬", "亀徳", "和泊", "本部"]:
        assert rows[name]["status"] == OperationStatusEnum.delayed
        assert "約2時間遅れて" in rows[name]["status_detail"]


@resp_mock.activate
def test_delayed_ship_without_port_notice_has_no_unmatched_warning(
    db_session, marue_with_ports
):
    """遅延の船は港の記載が無いのが普通なので port_notice_unmatched を出さない。"""
    company, ports = marue_with_ports
    departures, logs = run_with_ships(
        db_session, company, ("遅延", "荒天のため約2時間遅れて運航しております。")
    )

    rows = down_statuses(db_session, company, ports, departures)
    assert all(r["status"] == OperationStatusEnum.delayed for r in rows.values())
    assert not any(log["event"] == "port_notice_unmatched" for log in logs)


# ---------------------------------------------------------------------------
# 抜港 → skipped（specs/9-marue-port-skip）。保存版（2026-10-06 09:28）を使う
# ---------------------------------------------------------------------------

NOW_1006 = datetime(2026, 10, 6, 9, 28)
D1006 = "2026年10月06日"
NAMINOUE_22921 = (
    "https://www.aline-ferry.com/status/route-kagoshima/ferry-naminoue/22921/"
)
NAMINOUE_ARR = "2026年10月6日 18:20"
# 下りの各港（保存版の詳細ページの時刻。和泊・与論は通常ダイヤ）
DOWN_1006 = {
    NAZE: "2026年10月6日 06:30",
    KAMETOKU: "2026年10月6日 09:40",
    WADOMARI: "2026年10月6日 11:30",
    YORON: "2026年10月6日 13:50",
    MOTOBU: "2026年10月6日 16:30",
}
PORT_NAME_BY_CODE = {
    NAZE: "名瀬",
    KAMETOKU: "亀徳",
    WADOMARI: "和泊",
    YORON: "与論",
    MOTOBU: "本部",
}


def searches_1006(overrides: dict[str, str] | None = None) -> dict:
    """保存版の便検索。overrides は港コード → 検索結果の HTML（差し替え）。"""
    results = {
        (code, NAHA, D1006): search_html([marue("フェリー波之上", dep, NAMINOUE_ARR)])
        for code, dep in DOWN_1006.items()
    }
    for code, html in (overrides or {}).items():
        results[(code, NAHA, D1006)] = html
    return results


def mock_20261006(searches: dict | None = None, naminoue_detail: str | None = None):
    mock_search(searches if searches is not None else searches_1006())
    resp_mock.add(
        resp_mock.GET, KAGOSHIMA_URL, body=read_fixture("marue/kagoshima_20261006.html")
    )
    resp_mock.add(
        resp_mock.GET,
        "https://www.aline-ferry.com/status/route-kagoshima/ferry-akebono/21525/",
        body=read_fixture("marue/ship_detail_normal.html"),
    )
    resp_mock.add(
        resp_mock.GET,
        NAMINOUE_22921,
        body=naminoue_detail
        or read_fixture("marue/ship_detail_naminoue_20261006.html"),
    )


def run_1006(db_session, company_id):
    scraper = MarueFerry(db_session, company_id)
    with structlog.testing.capture_logs() as logs, fixed_now(NOW_1006):
        records = scraper.parse(scraper.fetch())
        departures = scraper.parse_departures()
    return scraper, records, departures, logs


def rows_1006(db_session, company, ports, departures):
    down, _ = routes_of(db_session, company)
    return {
        name: find(departures, down, ports[name], date(2026, 10, 6))
        for name in PORT_NAME_BY_CODE.values()
    }


def without_skip_lines(html: str) -> str:
    """保存版の詳細ページから「抜港」の2行を取り除く（「寄港いたしません」だけの版）。"""
    result, n = re.subn(
        r"<p>10月6日\(火\)(?:和泊|与論)港[^\n]*抜港[^\n]*</p>\n?", "", html
    )
    assert n == 2
    return result


def assert_saved_version_result(db_session, company, ports, departures, records):
    rows = rows_1006(db_session, company, ports, departures)
    assert rows["和泊"]["status"] == OperationStatusEnum.skipped
    assert rows["与論"]["status"] == OperationStatusEnum.skipped
    assert (
        "抜港" in rows["和泊"]["status_detail"]
        or "寄港いたしません" in rows["和泊"]["status_detail"]
    )
    assert rows["亀徳"]["status"] == OperationStatusEnum.delayed
    for name in ["名瀬", "本部"]:
        assert rows[name]["status"] == OperationStatusEnum.delayed
    assert not [r for r in departures if r["status"] == OperationStatusEnum.cancelled]
    assert not [r for r in records if r["status"] == OperationStatusEnum.skipped]


@resp_mock.activate
def test_saved_version_skips_wadomari_and_yoron(db_session, marue_with_ports):
    """保存版（2026-10-06）：和泊・与論 → skipped、亀徳 → delayed、欠航0件（SC-001・FR-010）。"""
    company, ports = marue_with_ports
    mock_20261006()

    _, records, departures, _ = run_1006(db_session, company.id)

    assert_saved_version_result(db_session, company, ports, departures, records)
    rows = rows_1006(db_session, company, ports, departures)
    assert "和泊港" in rows["和泊"]["status_detail"]


@resp_mock.activate
def test_saved_version_with_only_kikou_itashimasen(db_session, marue_with_ports):
    """「抜港」の行が無く「寄港いたしません」だけでも同じ結果（US3、FR-010）。"""
    company, ports = marue_with_ports
    mock_20261006(
        naminoue_detail=without_skip_lines(
            read_fixture("marue/ship_detail_naminoue_20261006.html")
        )
    )

    _, records, departures, _ = run_1006(db_session, company.id)

    assert_saved_version_result(db_session, company, ports, departures, records)
    rows = rows_1006(db_session, company, ports, departures)
    assert "寄港いたしません" in rows["和泊"]["status_detail"]


def test_saved_version_ship_info(db_session, marue_with_ports):
    """保存版の波之上：delayed・条件付・スケジュール変更（US4 シナリオ1）。"""
    company, _ = marue_with_ports
    scraper = MarueFerry(db_session, company.id)

    ship = scraper._parse_ships(read_fixture("marue/kagoshima_20261006.html"))[
        "フェリー波之上"
    ]

    assert ship.status == OperationStatusEnum.delayed
    assert ship.conditional is True
    assert ship.schedule_changed is True


def test_tag_order_does_not_change_result(db_session, marue_with_ports):
    """タグの並びを入れ替えても ShipInfo は同じ（SC-004）。"""
    company, _ = marue_with_ports
    scraper = MarueFerry(db_session, company.id)
    html = read_fixture("marue/kagoshima_20261006.html")
    swapped = re.sub(
        r'(<span class="tag-sche">スケジュール変更</span>)(\s*)(<span class="tag-conditionally">条件付運航</span>)',
        r"\3\2\1",
        html,
    )
    assert swapped != html

    assert scraper._parse_ships(swapped) == scraper._parse_ships(html)


def test_cancelled_tag_wins_over_conditional(db_session, marue_with_ports):
    """「欠航」＋「条件付運航」→ 欠航（一番重いもの。US4 シナリオ3）。"""
    company, _ = marue_with_ports
    scraper = MarueFerry(db_session, company.id)
    html = read_fixture("marue/kagoshima_20261006.html").replace(
        '<span class="tag-sche">スケジュール変更</span>',
        '<span class="tag-cancel">欠航</span>',
    )

    ship = scraper._parse_ships(html)["フェリー波之上"]

    assert ship.status == OperationStatusEnum.cancelled
    assert ship.conditional is True


def test_unknown_tag_is_ignored_with_warning(db_session, marue_with_ports):
    company, _ = marue_with_ports
    scraper = MarueFerry(db_session, company.id)
    html = read_fixture("marue/kagoshima_20261006.html").replace(
        '<span class="tag-sche">スケジュール変更</span>',
        '<span class="tag-x">謎のタグ</span>',
    )

    with structlog.testing.capture_logs() as logs:
        ship = scraper._parse_ships(html)["フェリー波之上"]

    assert ship.status == OperationStatusEnum.delayed
    assert ship.conditional is True
    assert ship.schedule_changed is False
    assert any(log["event"] == "unknown_status_text" for log in logs)


def test_port_change_tag_is_conditional(db_session, marue_with_ports):
    """「寄港地変更」タグだけでも条件付（delayed）として読み、unknown_status_text にしない。"""
    company, _ = marue_with_ports
    scraper = MarueFerry(db_session, company.id)
    original = read_fixture("marue/kagoshima_20261006.html")
    html = re.sub(
        r'<span class="tag-sche">スケジュール変更</span>\s*<span class="tag-conditionally">条件付運航</span>',
        '<span class="tag-port">寄港地変更</span>',
        original,
    )
    assert html != original

    with structlog.testing.capture_logs() as logs:
        ship = scraper._parse_ships(html)["フェリー波之上"]

    assert ship.status == OperationStatusEnum.delayed
    assert ship.conditional is True
    assert ship.schedule_changed is False
    assert not [log for log in logs if log["event"] == "unknown_status_text"]


@resp_mock.activate
def test_cancelled_ship_makes_every_port_cancelled_not_skipped(
    db_session, marue_with_ports
):
    """船が欠航なら、抜港の告知があっても全港 cancelled（FR-005・SC-003）。"""
    company, ports = marue_with_ports
    html = read_fixture("marue/kagoshima_20261006.html").replace(
        '<span class="tag-sche">スケジュール変更</span>',
        '<span class="tag-cancel">欠航</span>',
    )
    mock_search(searches_1006())
    resp_mock.add(resp_mock.GET, KAGOSHIMA_URL, body=html)
    resp_mock.add(
        resp_mock.GET,
        "https://www.aline-ferry.com/status/route-kagoshima/ferry-akebono/21525/",
        body=read_fixture("marue/ship_detail_normal.html"),
    )
    resp_mock.add(
        resp_mock.GET,
        NAMINOUE_22921,
        body=read_fixture("marue/ship_detail_naminoue_20261006.html"),
    )

    _, _, departures, _ = run_1006(db_session, company.id)

    rows = rows_1006(db_session, company, ports, departures)
    assert all(r["status"] == OperationStatusEnum.cancelled for r in rows.values())
    assert not [r for r in departures if r["status"] == OperationStatusEnum.skipped]


@resp_mock.activate
def test_conditional_only_ship_keeps_unmentioned_ports_operating(
    db_session, marue_with_ports
):
    """条件付だけの船は言及の無い港が operating、条件付＋スケジュール変更は delayed（research R5）。"""
    company, ports = marue_with_ports
    mock_20261006()
    html = read_fixture("marue/kagoshima_20261006.html").replace(
        '<span class="tag-sche">スケジュール変更</span>', ""
    )
    resp_mock.replace(resp_mock.GET, KAGOSHIMA_URL, body=html)

    _, _, departures, _ = run_1006(db_session, company.id)

    rows = rows_1006(db_session, company, ports, departures)
    assert rows["和泊"]["status"] == OperationStatusEnum.skipped
    assert rows["亀徳"]["status"] == OperationStatusEnum.delayed
    assert rows["名瀬"]["status"] == OperationStatusEnum.operating
    assert rows["本部"]["status"] == OperationStatusEnum.operating


# ---- 時刻・便が無い抜港の港（research R6）----------------------------------

DASH_ROW = ("フェリー波之上", "－", "－", "マルエーフェリー")


@resp_mock.activate
def test_search_row_without_datetime_is_kept_with_warning(db_session, marue_with_ports):
    company, _ = marue_with_ports
    mock_20261006(searches_1006({YORON: search_html([DASH_ROW])}))

    scraper, _, _, logs = run_1006(db_session, company.id)

    rows = scraper._searches[
        (
            routes_of(db_session, company)[0].id,
            _port_id(db_session, "与論"),
            date(2026, 10, 6),
        )
    ]
    assert (
        rows is not None and rows[0].departure_at is None and rows[0].arrival_at is None
    )
    assert any(log["event"] == "search_datetime_missing" for log in logs)


def _port_id(db_session, name):
    from scraper.db.models import Port

    return db_session.execute(select(Port.id).where(Port.name == name)).scalar()


@resp_mock.activate
def test_skipped_port_without_datetime_is_skipped_without_time(
    db_session, marue_with_ports
):
    company, ports = marue_with_ports
    mock_20261006(searches_1006({YORON: search_html([DASH_ROW])}))

    _, _, departures, _ = run_1006(db_session, company.id)

    row = rows_1006(db_session, company, ports, departures)["与論"]
    assert row["status"] == OperationStatusEnum.skipped
    assert row["scheduled_departure_at"] is None and row["scheduled_arrival_at"] is None
    assert row["ship_name"] == "フェリー波之上"
    assert "与論港" in row["status_detail"]


@resp_mock.activate
def test_not_skipped_port_without_datetime_is_not_written(db_session, marue_with_ports):
    """抜港でない港（名瀬）の日時なしの行は書かない。"""
    company, ports = marue_with_ports
    mock_20261006(searches_1006({NAZE: search_html([DASH_ROW])}))
    down, _ = routes_of(db_session, company)

    _, _, departures, logs = run_1006(db_session, company.id)

    assert not [
        r
        for r in departures
        if r["route_id"] == down.id
        and r["port_id"] == ports["名瀬"].id
        and r["departure_date"] == date(2026, 10, 6)
    ]
    assert any(log["event"] == "search_row_without_datetime_skipped" for log in logs)


@resp_mock.activate
def test_skipped_port_without_datetime_on_other_date_is_not_written(
    db_session, marue_with_ports
):
    """今の便は 10/6 着なのに、10/8 の与論発に日時なしの行 → 書かない（出港日が合わない）。"""
    company, ports = marue_with_ports
    searches = searches_1006()
    searches[(YORON, NAHA, "2026年10月08日")] = search_html([DASH_ROW])
    mock_20261006(searches)
    down, _ = routes_of(db_session, company)

    _, _, departures, _ = run_1006(db_session, company.id)

    assert not [
        r
        for r in departures
        if r["route_id"] == down.id
        and r["port_id"] == ports["与論"].id
        and r["departure_date"] == date(2026, 10, 8)
    ]


@resp_mock.activate
def test_skipped_port_with_empty_search_is_skipped_with_ship_name(
    db_session, marue_with_ports
):
    """与論発の検索が0件でも、今の便の抜港の日なら skipped（船名つき・時刻なし）。"""
    company, ports = marue_with_ports
    mock_20261006(searches_1006({YORON: read_fixture("marue/search_empty.html")}))

    _, _, departures, _ = run_1006(db_session, company.id)

    row = rows_1006(db_session, company, ports, departures)["与論"]
    assert row["status"] == OperationStatusEnum.skipped
    assert row["ship_name"] == "フェリー波之上"
    assert row["scheduled_departure_at"] is None
    assert "与論港" in row["status_detail"]


@resp_mock.activate
def test_empty_search_for_not_skipped_port_or_other_date_is_no_service(
    db_session, marue_with_ports
):
    company, ports = marue_with_ports
    searches = searches_1006({NAZE: read_fixture("marue/search_empty.html")})
    searches[(YORON, NAHA, "2026年10月07日")] = read_fixture("marue/search_empty.html")
    mock_20261006(searches)
    down, _ = routes_of(db_session, company)

    _, _, departures, _ = run_1006(db_session, company.id)

    assert (
        rows_1006(db_session, company, ports, departures)["名瀬"]["status"]
        == OperationStatusEnum.no_service
    )
    assert (
        find(departures, down, ports["与論"], date(2026, 10, 7))["status"]
        == OperationStatusEnum.no_service
    )


@resp_mock.activate
def test_no_current_voyage_does_not_create_skipped(db_session, marue_with_ports):
    """今の便が決まらない（船ブロックに無い）→ skipped を作らない。"""
    company, ports = marue_with_ports
    html = read_fixture("marue/kagoshima_20261006.html").replace(
        "フェリー波之上", "フェリー別船"
    )
    mock_20261006(searches_1006({YORON: read_fixture("marue/search_empty.html")}))
    resp_mock.replace(resp_mock.GET, KAGOSHIMA_URL, body=html)

    _, _, departures, _ = run_1006(db_session, company.id)

    assert not [r for r in departures if r["status"] == OperationStatusEnum.skipped]


# ---------------------------------------------------------------------------
# 便ごとの状態（保存版 2026-10-20：あけぼのは 20日上り＝条件付・寄港地変更、21日下り・23日上り＝欠航）
# ---------------------------------------------------------------------------

NOW_1020 = datetime(2026, 10, 20, 11, 39)
D1020 = "2026年10月20日"
D1021 = "2026年10月21日"
AKEBONO_21394 = (
    "https://www.aline-ferry.com/status/route-kagoshima/ferry-akebono/21394/"
)
NAMINOUE_21162 = (
    "https://www.aline-ferry.com/status/route-kagoshima/ferry-naminoue/21162/"
)
AKEBONO_UP_ARR = "2026年10月21日 08:30"
# あけぼの：10/20 那覇発の上り。10/21 鹿児島発の下りは欠航で検索に出ない
UP_1020 = {
    NAHA: "2026年10月20日 07:00",
    MOTOBU: "2026年10月20日 09:20",
    YORON: "2026年10月20日 12:10",
    WADOMARI: "2026年10月20日 14:40",
    KAMETOKU: "2026年10月20日 17:00",
    NAZE: "2026年10月20日 21:20",
}


def run_1020(db_session, company_id, kagoshima: str | None = None):
    mock_search(
        {
            (code, KAGOSHIMA, D1020): search_html(
                [marue("フェリーあけぼの", dep, AKEBONO_UP_ARR)]
            )
            for code, dep in UP_1020.items()
        }
    )
    resp_mock.add(
        resp_mock.GET,
        KAGOSHIMA_URL,
        body=kagoshima or read_fixture("marue/kagoshima_20261020.html"),
    )
    resp_mock.add(
        resp_mock.GET,
        AKEBONO_21394,
        body=read_fixture("marue/ship_detail_akebono_20261020.html"),
    )
    resp_mock.add(
        resp_mock.GET,
        NAMINOUE_21162,
        body=read_fixture("marue/ship_detail_normal.html"),
    )
    scraper = MarueFerry(db_session, company_id)
    with structlog.testing.capture_logs() as logs, fixed_now(NOW_1020):
        records = scraper.parse(scraper.fetch())
        departures = scraper.parse_departures()
    return scraper, records, departures, logs


def test_voyages_are_read_from_excerpt(db_session, marue_with_ports):
    """抜粋の「■10月20日(火)那覇発上り便…」を便ごとに読む（年は今日に近いほう）。"""
    company, _ = marue_with_ports
    scraper = MarueFerry(db_session, company.id)

    with fixed_now(NOW_1020), structlog.testing.capture_logs() as logs:
        ships = scraper._parse_ships(read_fixture("marue/kagoshima_20261020.html"))

    # 本番そのままの <span class="tag-port">寄港地変更</span> も読める
    assert not [log for log in logs if log["event"] == "unknown_status_text"]
    akebono = ships["フェリーあけぼの"]
    assert akebono.status == OperationStatusEnum.cancelled
    assert [(v.departure_date, v.direction, v.status) for v in akebono.voyages] == [
        (date(2026, 10, 20), "上り", OperationStatusEnum.delayed),
        (date(2026, 10, 21), "下り", OperationStatusEnum.cancelled),
        (date(2026, 10, 23), "上り", OperationStatusEnum.cancelled),
    ]
    assert akebono.voyages[0].conditional is True
    assert akebono.voyages[0].schedule_changed is False
    assert [
        (v.departure_date, v.direction) for v in ships["フェリー波之上"].voyages
    ] == [(date(2026, 10, 19), "下り")]


def test_voyages_read_slash_date_format(db_session, marue_with_ports):
    """「10/5(月)鹿児島新港18:00発／下り便…スケジュール変更・条件付運航」も読む。"""
    company, _ = marue_with_ports
    scraper = MarueFerry(db_session, company.id)

    with fixed_now(NOW_1006):
        ship = scraper._parse_ships(read_fixture("marue/kagoshima_20261006.html"))[
            "フェリー波之上"
        ]

    assert len(ship.voyages) == 1
    voyage = ship.voyages[0]
    assert (voyage.departure_date, voyage.direction) == (date(2026, 10, 5), "下り")
    assert voyage.status == OperationStatusEnum.delayed
    assert voyage.conditional is True and voyage.schedule_changed is True


@resp_mock.activate
def test_other_voyage_cancellation_does_not_cancel_current_voyage(
    db_session, marue_with_ports
):
    """別の便の「欠航」タグが今の便に付かない：20日上りは与論・亀徳だけ delayed、他は operating。"""
    company, ports = marue_with_ports
    _, up = routes_of(db_session, company)

    _, records, departures, _ = run_1020(db_session, company.id)

    rows = {
        name: find(departures, up, ports[name], date(2026, 10, 20)) for name in UP_PORTS
    }
    assert rows["与論"]["status"] == OperationStatusEnum.delayed
    assert "与論港" in rows["与論"]["status_detail"]
    assert rows["亀徳"]["status"] == OperationStatusEnum.delayed
    assert "平土野港" in rows["亀徳"]["status_detail"]
    for name in ["本部", "和泊", "名瀬"]:
        assert rows[name]["status"] == OperationStatusEnum.operating
    assert not [r for r in departures if r["status"] == OperationStatusEnum.cancelled]

    route = next(r for r in records if r["route_id"] == up.id)
    assert route["status"] == OperationStatusEnum.delayed


@resp_mock.activate
def test_departed_voyage_not_in_excerpt_keeps_ship_status(db_session, marue_with_ports):
    """抜粋に今の便の行が無くても、出港済みで記録も無ければ船のステータスのまま（R2・R7）+ voyage_not_in_excerpt。"""
    company, ports = marue_with_ports
    _, up = routes_of(db_session, company)
    html = read_fixture("marue/kagoshima_20261020.html").replace(
        "■10月20日(火)那覇発上り便", "■10月22日(木)那覇発上り便"
    )

    _, _, departures, logs = run_1020(db_session, company.id, html)

    assert (
        find(departures, up, ports["名瀬"], date(2026, 10, 20))["status"]
        == OperationStatusEnum.cancelled
    )
    # 港の行ごとに呼ばれても警告は1回
    warnings = [log for log in logs if log["event"] == "voyage_not_in_excerpt"]
    assert len(warnings) == 1
    assert warnings[0]["assumed"] == "ship_status"


@pytest.mark.parametrize(
    "line",
    [
        "■10月20日(火)那覇発上り便…条件付き運航（与論港は欠航の可能性あり）",
        "■10月20日(火)那覇発上り便…条件付き運航※天候によっては欠航となる場合があります。",
    ],
)
def test_voyage_status_ignores_notes_after_status(db_session, marue_with_ports, line):
    """便の行の補足に「欠航」があっても、状態の語（条件付き運航）だけで判定する。"""
    company, _ = marue_with_ports
    scraper = MarueFerry(db_session, company.id)
    html = read_fixture("marue/kagoshima_20261020.html").replace(
        "■10月20日(火)那覇発上り便…条件付き運航・寄港地変更", line
    )
    assert html != read_fixture("marue/kagoshima_20261020.html")

    with fixed_now(NOW_1020):
        voyages = scraper._parse_ships(html)["フェリーあけぼの"].voyages

    assert voyages[0].departure_date == date(2026, 10, 20)
    assert voyages[0].status == OperationStatusEnum.delayed
    assert voyages[0].conditional is True
    assert [v.status for v in voyages[1:]] == [OperationStatusEnum.cancelled] * 2


# ---------------------------------------------------------------------------
# 先の便・臨時便（保存版 2026-10-26：波之上は 10/27 那覇発上り＝欠航、10/26 鹿児島発下り・10/28 那覇発上り＝臨時便運航）
# ---------------------------------------------------------------------------

NOW_1026 = datetime(2026, 10, 26, 10, 50)
AKEBONO_17809 = (
    "https://www.aline-ferry.com/status/route-kagoshima/ferry-akebono/17809/"
)
NAMINOUE_25492 = (
    "https://www.aline-ferry.com/status/route-kagoshima/ferry-naminoue/25492/"
)


def _voyage_searches(
    ship: str, origin_code_to_dep: dict[str, str], end_code: str, day: str, arr: str
) -> dict[tuple[str, str, str], str]:
    return {
        (code, end_code, day): search_html([marue(ship, dep, arr)])
        for code, dep in origin_code_to_dep.items()
    }


def down_1025_rows() -> dict[tuple[str, str, str], str]:
    """波之上の 10/25 鹿児島発下り（今の便）の 10/26 ぶんの検索結果。本番の DB と同じ時刻。"""
    return _voyage_searches(
        "フェリー波之上",
        {
            NAZE: "2026年10月26日 05:50",
            KAMETOKU: "2026年10月26日 09:40",
            WADOMARI: "2026年10月26日 12:00",
            YORON: "2026年10月26日 14:10",
            MOTOBU: "2026年10月26日 17:10",
        },
        NAHA,
        "2026年10月26日",
        "2026年10月26日 19:00",
    )


def up_1027_rows() -> dict[tuple[str, str, str], str]:
    """波之上の 10/27 那覇発上り（先の便）の検索結果。"""
    return _voyage_searches(
        "フェリー波之上",
        {
            NAHA: "2026年10月27日 07:00",
            MOTOBU: "2026年10月27日 09:20",
            YORON: "2026年10月27日 12:10",
            WADOMARI: "2026年10月27日 14:40",
            KAMETOKU: "2026年10月27日 17:00",
            NAZE: "2026年10月27日 21:20",
        },
        KAGOSHIMA,
        "2026年10月27日",
        "2026年10月28日 08:30",
    )


def run_1026(
    db_session,
    company_id,
    searches,
    *,
    now: datetime = NOW_1026,
    kagoshima: str | None = None,
):
    """保存版 2026-10-26 の鹿児島航路ページと詳細ページで fetch → parse → parse_departures する。"""
    mock_search(searches)
    resp_mock.add(
        resp_mock.GET,
        KAGOSHIMA_URL,
        body=kagoshima or read_fixture("marue/kagoshima_20261026.html"),
    )
    resp_mock.add(
        resp_mock.GET,
        AKEBONO_17809,
        body=read_fixture("marue/ship_detail_akebono_20261026.html"),
    )
    resp_mock.add(
        resp_mock.GET,
        NAMINOUE_25492,
        body=read_fixture("marue/ship_detail_naminoue_20261026.html"),
    )
    scraper = MarueFerry(db_session, company_id)
    with structlog.testing.capture_logs() as logs, fixed_now(now):
        records = scraper.parse(scraper.fetch())
        departures = scraper.parse_departures()
    # 詳細ページのモック漏れがあると港別情報の確認が空振りになる
    assert not [log for log in logs if log["event"] == "ship_detail_fetch_failed"]
    return scraper, records, departures, logs


# ---------------------------------------------------------------------------
# 便の行の照合（_voyage_line）
# ---------------------------------------------------------------------------


def test_voyage_lines_know_whether_they_start_midway(db_session, marue_with_ports):
    """途中の港から書いた行だけ from_midway（港名は PortResolver で引く）。"""
    company, _ = marue_with_ports
    scraper = MarueFerry(db_session, company.id)

    with fixed_now(NOW_1026):
        ship = scraper._parse_ships(read_fixture("marue/kagoshima_20261026.html"))[
            "フェリー波之上"
        ]
    assert ship.voyages[0].departure_date == date(2026, 10, 27)
    assert ship.voyages[0].from_midway is False  # 那覇港発上り

    def midway(line: str) -> bool:
        html = read_fixture("marue/kagoshima_20261026.html").replace(
            "■10月27日（火）那覇港発上り便", line
        )
        with fixed_now(NOW_1026):
            ship = scraper._parse_ships(html)["フェリー波之上"]
        return ship.voyages[0].from_midway

    assert midway("■10月22日（木）名瀬発下り便") is True
    assert midway("■10月22日（木）名瀬発那覇行き下り便") is True
    assert midway("■10月22日（木）名瀬 下り便") is True  # 「発」なし
    assert (
        midway("■10月27日（火）名瀬経由 那覇港発上り便") is False
    )  # 経由の港でなく発の港
    assert midway("■10月27日（火）上り便") is False  # 港名なし
    assert midway("■10月27日（火）鹿児島新港18:00発／下り便") is False  # 始発港


@resp_mock.activate
def test_voyage_line_prefers_departure_date_over_range(db_session, marue_with_ports):
    company, _ = marue_with_ports
    down, up = routes_of(db_session, company)
    scraper = MarueFerry(db_session, company.id)
    with fixed_now(NOW_1026):
        ship = scraper._parse_ships(read_fixture("marue/kagoshima_20261026.html"))[
            "フェリー波之上"
        ]
        line = scraper._voyage_line(ship, up.id, date(2026, 10, 27), date(2026, 10, 28))
    assert line.departure_date == date(2026, 10, 27)
    assert line.status == OperationStatusEnum.cancelled


def kagoshima_1026(lines: str | None = None, tags: list[str] | None = None) -> str:
    """保存版 2026-10-26 の波之上のブロックの、抜粋の便の行（<br> 区切り）とタグを差し替える。"""
    html = read_fixture("marue/kagoshima_20261026.html")
    if lines is not None:
        html, n = re.subn(
            r'(フェリー波之上</div>.*?<div class="situation-excerpt">).*?(</div>)',
            rf"\g<1>{lines}\g<2>",
            html,
            count=1,
            flags=re.S,
        )
        assert n == 1
    if tags is not None:
        spans = "".join(f'<span class="tag-canceled">{t}</span>' for t in tags)
        html, n = re.subn(
            r'(フェリー波之上</div>.*?<div class="tag-list">).*?(</div>)',
            rf"\g<1>{spans}\g<2>",
            html,
            count=1,
            flags=re.S,
        )
        assert n == 1
    return html


def _ship_with(scraper, lines: str):
    """波之上の抜粋の便の行を差し替えて読む。"""
    with fixed_now(NOW_1026):
        return scraper._parse_ships(kagoshima_1026(lines))["フェリー波之上"]


def test_voyage_line_range_only_for_lines_from_midway(db_session, marue_with_ports):
    company, _ = marue_with_ports
    down, up = routes_of(db_session, company)
    scraper = MarueFerry(db_session, company.id)

    # 始発港の行・港名の無い行は、範囲では合わない
    for line in ("■10月28日（水）那覇港発上り便…欠航", "■10月28日（水）上り便…欠航"):
        ship = _ship_with(scraper, line)
        with fixed_now(NOW_1026):
            assert (
                scraper._voyage_line(
                    ship, up.id, date(2026, 10, 27), date(2026, 10, 28)
                )
                is None
            )

    # 途中の港の行は、出港日〜到着日の範囲で合う
    ship = _ship_with(scraper, "■10月28日（水）名瀬発上り便…欠航")
    with fixed_now(NOW_1026):
        line = scraper._voyage_line(ship, up.id, date(2026, 10, 27), date(2026, 10, 28))
        assert line is not None and line.departure_date == date(2026, 10, 28)
        # 範囲の外、方向違いは合わない
        assert (
            scraper._voyage_line(ship, up.id, date(2026, 10, 29), date(2026, 10, 30))
            is None
        )
        assert (
            scraper._voyage_line(ship, down.id, date(2026, 10, 27), date(2026, 10, 28))
            is None
        )


# ---------------------------------------------------------------------------
# 先の便（US1）
# ---------------------------------------------------------------------------

DOWN_PORT_NAMES = ["鹿児島", "名瀬", "亀徳", "和泊", "与論", "本部"]
UP_1028_ROWS = _voyage_searches(
    "フェリー波之上",
    {
        NAHA: "2026年10月28日 05:00",
        MOTOBU: "2026年10月28日 07:20",
        YORON: "2026年10月28日 10:10",
        WADOMARI: "2026年10月28日 12:40",
        KAMETOKU: "2026年10月28日 15:00",
        NAZE: "2026年10月28日 19:20",
    },
    KAGOSHIMA,
    "2026年10月28日",
    "2026年10月29日 07:30",
)


@resp_mock.activate
def test_future_voyage_gets_voyage_line_status(db_session, marue_with_ports):
    """SC-001：10/27 那覇発上りは全港「欠航」。今の便（10/25 鹿児島発）の 10/26 の行は今までどおり。"""
    company, ports = marue_with_ports
    down, up = routes_of(db_session, company)

    _, _, departures, _ = run_1026(
        db_session, company.id, {**down_1025_rows(), **up_1027_rows()}
    )

    for name in UP_PORTS:
        row = find(departures, up, ports[name], date(2026, 10, 27))
        assert row["status"] == OperationStatusEnum.cancelled, name
        assert "10月27日（火）那覇港発上り便…欠航" in row["status_detail"]
    for name in ["和泊", "与論", "本部"]:
        row = find(departures, down, ports[name], date(2026, 10, 26))
        assert row["status"] == OperationStatusEnum.cancelled, name


@resp_mock.activate
def test_future_voyage_line_status_ignores_port_notices(db_session, marue_with_ports):
    """先の便の行が「条件付運航」なら全港 delayed。詳細ページの「寄港いたしません」で抜港にしない（FR-004）。"""
    company, ports = marue_with_ports
    _, up = routes_of(db_session, company)
    # 行が2つ以上あれば行の状態を使う（1つだけならタグ）
    lines = "■10月27日（火）那覇港発上り便…条件付運航<br />■10月23日（金）鹿児島新港発下り便…欠航"

    _, _, departures, _ = run_1026(
        db_session,
        company.id,
        {**down_1025_rows(), **up_1027_rows()},
        kagoshima=kagoshima_1026(lines),
    )

    for name in UP_PORTS:
        row = find(departures, up, ports[name], date(2026, 10, 27))
        assert row["status"] == OperationStatusEnum.delayed, name
        assert row["status_detail"]


@resp_mock.activate
def test_future_voyage_without_line_stays_scheduled(db_session, marue_with_ports):
    """SC-004：抜粋に行の無い先の便は運航予定のまま（status・status_detail ともに None）。"""
    company, ports = marue_with_ports
    down, _ = routes_of(db_session, company)
    searches = {
        **down_1025_rows(),
        (KAGOSHIMA, NAHA, "2026年10月29日"): search_html(
            [marue("フェリー波之上", "2026年10月29日 18:00", "2026年10月30日 19:00")]
        ),
    }

    _, _, departures, _ = run_1026(db_session, company.id, searches)

    row = find(departures, down, ports["鹿児島"], date(2026, 10, 29))
    assert row["status"] is None and row["status_detail"] is None


@resp_mock.activate
def test_future_voyage_with_single_line_uses_ship_tag(db_session, marue_with_ports):
    """便の行が1つだけで先の便に合う → 船のタグのステータス（抜粋の文より確か）。"""
    company, ports = marue_with_ports
    _, up = routes_of(db_session, company)

    _, _, departures, _ = run_1026(
        db_session,
        company.id,
        {**down_1025_rows(), **up_1027_rows()},
        kagoshima=kagoshima_1026("■10月27日（火）那覇港発上り便…条件付運航"),
    )

    for name in UP_PORTS:
        row = find(departures, up, ports[name], date(2026, 10, 27))
        assert row["status"] == OperationStatusEnum.cancelled, name


@resp_mock.activate
def test_future_extra_voyage_line_is_operating(db_session, marue_with_ports):
    """「臨時便運航」の先の便は operating で詳細なし。
    ※本番では臨時便は便検索に出てこない（spec の範囲外）。ここで流す検索結果は仮のデータ。
    """
    company, ports = marue_with_ports
    _, up = routes_of(db_session, company)

    _, _, departures, _ = run_1026(
        db_session,
        company.id,
        {**down_1025_rows(), **up_1027_rows(), **UP_1028_ROWS},
    )

    for name in UP_PORTS:
        row = find(departures, up, ports[name], date(2026, 10, 28))
        assert row["status"] == OperationStatusEnum.operating, name
        assert row["status_detail"] is None


@resp_mock.activate
def test_far_search_is_forced_only_for_keys_from_voyage_lines(
    db_session, marue_with_ports
):
    """SC-005：便の行から決まる 2日先以降のキーは、確認済みでも検索する。行の無い日付は今までどおり飛ばす。
    ※抜粋の「10/28 那覇港発上り便」は、本番では臨時便の行。キーの決め方だけを確かめる仮のデータ。
    """
    company, ports = marue_with_ports
    down, up = routes_of(db_session, company)
    checked = NOW_1026 - timedelta(hours=1)
    for route, names in ((down, DOWN_PORT_NAMES), (up, UP_PORTS)):
        for name in names:
            for d in (date(2026, 10, 28), date(2026, 10, 29)):
                db_session.add(
                    DepartureStatus(
                        route_id=route.id,
                        port_id=ports[name].id,
                        departure_date=d,
                        ship_name="",
                        status="no_service",
                        content_hash="x" * 64,
                        scraped_at=checked,
                        checked_at=checked,
                    )
                )
    db_session.commit()

    run_1026(
        db_session,
        company.id,
        {**up_1027_rows(), **UP_1028_ROWS},
        kagoshima=kagoshima_1026("■10月28日（水）那覇港発上り便…欠航"),
    )

    far = {c for c in search_calls() if c[2] in ("2026年10月28日", "2026年10月29日")}
    assert far == {
        (code, KAGOSHIMA, "2026年10月28日")
        for code in (NAHA, MOTOBU, YORON, WADOMARI, KAMETOKU, NAZE)
    }


# ---------------------------------------------------------------------------
# 「臨時便運航」の読み取り（US2）
# ---------------------------------------------------------------------------


def test_extra_voyage_status_is_read_without_warnings(db_session, marue_with_ports):
    """SC-002：「臨時便運航」を operating として読み、警告を出さない。船のステータスは一番重い「欠航」。"""
    company, _ = marue_with_ports
    scraper = MarueFerry(db_session, company.id)

    with fixed_now(NOW_1026), structlog.testing.capture_logs() as logs:
        ship = scraper._parse_ships(read_fixture("marue/kagoshima_20261026.html"))[
            "フェリー波之上"
        ]

    assert not [
        log
        for log in logs
        if log["event"] in ("unknown_status_text", "unknown_voyage_status")
    ]
    assert ship.status == OperationStatusEnum.cancelled
    assert [(v.departure_date, v.direction, v.status) for v in ship.voyages] == [
        (date(2026, 10, 27), "上り", OperationStatusEnum.cancelled),
        (date(2026, 10, 26), "下り", OperationStatusEnum.operating),
        (date(2026, 10, 28), "上り", OperationStatusEnum.operating),
    ]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("臨時便運航", OperationStatusEnum.operating),
        ("臨時便運休", OperationStatusEnum.suspended),
        ("臨時便条件付運航", OperationStatusEnum.delayed),
        ("臨時便欠航", OperationStatusEnum.cancelled),
        # 休・欠を含むのに「欠航」「運休」の語が無い言い方は、運航にせず読めない扱い（警告が出る）
        ("臨時休航", None),
        ("臨時欠便", None),
    ],
)
def test_extra_voyage_text_does_not_hide_heavier_words(
    db_session, marue_with_ports, text, expected
):
    """「臨時」は最後の手がかり。運休・条件付・欠航の語があればそちらを先に当てる。"""
    company, _ = marue_with_ports
    assert MarueFerry(db_session, company.id)._parse_status_text(text) == expected


# ---------------------------------------------------------------------------
# 今の便に合う行が無いとき（US3・FR-011）
# ---------------------------------------------------------------------------

NAMINOUE = "フェリー波之上"
DOWN_1029_ARR = "2026年10月30日 19:00"
ALL_DOWN_PORTS = ["鹿児島", "名瀬", "亀徳", "和泊", "与論", "本部"]
LINES_0_TO_2 = (
    "■10月27日（火）那覇港発上り便…{first}<br />"
    "■10月26日（月）鹿児島新港発下り便…臨時便運航<br />"
    "■10月28日（水）那覇港発上り便…臨時便運航"
)


def down_1029_rows(
    ports_1030: tuple[str, ...] = (NAZE, KAMETOKU, WADOMARI, YORON, MOTOBU),
) -> dict[tuple[str, str, str], str]:
    """波之上の 10/29 鹿児島発下り（10/30 19:00 着）の検索結果。10/29 は鹿児島だけ、10/30 は途中の港。"""
    times = {
        NAZE: "05:50",
        KAMETOKU: "09:40",
        WADOMARI: "12:00",
        YORON: "14:10",
        MOTOBU: "17:10",
    }
    return {
        **_voyage_searches(
            NAMINOUE,
            {KAGOSHIMA: "2026年10月29日 18:00"},
            NAHA,
            "2026年10月29日",
            DOWN_1029_ARR,
        ),
        **_voyage_searches(
            NAMINOUE,
            {code: f"2026年10月30日 {times[code]}" for code in ports_1030},
            NAHA,
            "2026年10月30日",
            DOWN_1029_ARR,
        ),
    }


def record_down_1029(
    db_session,
    down,
    ports,
    name,
    d,
    status,
    detail=None,
    *,
    checked=None,
    timeless=False,
):
    """前回の実行で記録した、波之上の 10/29 鹿児島発下りの行。"""
    dep = {
        "鹿児島": datetime(2026, 10, 29, 18, 0),
        "名瀬": datetime(2026, 10, 30, 5, 50),
        "亀徳": datetime(2026, 10, 30, 9, 40),
        "和泊": datetime(2026, 10, 30, 12, 0),
        "与論": datetime(2026, 10, 30, 14, 10),
        "本部": datetime(2026, 10, 30, 17, 10),
    }[name]
    when = checked or datetime(2026, 10, 29, 12, 0)
    db_session.add(
        DepartureStatus(
            route_id=down.id,
            port_id=ports[name].id,
            departure_date=d,
            ship_name=NAMINOUE,
            status=status,
            status_detail=detail,
            scheduled_departure_at=None if timeless else dep,
            scheduled_arrival_at=datetime(2026, 10, 30, 19, 0),
            content_hash="x" * 64,
            scraped_at=when,
            checked_at=when,
        )
    )
    db_session.commit()


def rows_1029(departures, down, ports):
    """10/29 鹿児島発の便の6港の行（鹿児島は 10/29、ほかは 10/30）。"""
    return {
        name: find(
            departures,
            down,
            ports[name],
            date(2026, 10, 29) if name == "鹿児島" else date(2026, 10, 30),
        )
        for name in ALL_DOWN_PORTS
    }


NOW_1028 = datetime(
    2026, 10, 28, 12, 0
)  # 10/27 便が着いて、今の便が 10/29 便に移った後
NOW_1029_EVE = datetime(2026, 10, 29, 20, 0)  # 10/29 18:00 に出港した後


@resp_mock.activate
def test_current_voyage_not_in_lines_is_operating(db_session, marue_with_ports):
    """SC-006：他の便の欠航しか書いていないとき、出港前の 10/29 便は全港 operating。
    詳細ページの臨時便の「寄港いたしません」を当てない（H4）。"""
    company, ports = marue_with_ports
    down, _ = routes_of(db_session, company)

    _, _, departures, logs = run_1026(
        db_session, company.id, down_1029_rows(), now=NOW_1028
    )

    for name, row in rows_1029(departures, down, ports).items():
        assert row["status"] == OperationStatusEnum.operating, name
        assert row["status_detail"] is None, name
    warning = next(log for log in logs if log["event"] == "voyage_not_in_excerpt")
    assert warning["assumed"] == "operating"


@resp_mock.activate
def test_single_other_voyage_line_still_makes_current_operating(
    db_session, marue_with_ports
):
    company, ports = marue_with_ports
    down, _ = routes_of(db_session, company)

    _, _, departures, _ = run_1026(
        db_session,
        company.id,
        down_1029_rows(),
        now=NOW_1028,
        kagoshima=kagoshima_1026("■10月27日（火）那覇港発上り便…欠航"),
    )

    for name, row in rows_1029(departures, down, ports).items():
        assert row["status"] == OperationStatusEnum.operating, name


@resp_mock.activate
def test_departed_current_voyage_does_not_take_departure_day_line(
    db_session, marue_with_ports
):
    """今の便（10/25 鹿児島発、出港済み）に、10/26 鹿児島発の臨時便の行が範囲で当たらない。"""
    company, ports = marue_with_ports
    down, _ = routes_of(db_session, company)

    _, _, departures, _ = run_1026(db_session, company.id, down_1025_rows())

    for name in ["和泊", "与論", "本部"]:
        row = find(departures, down, ports[name], date(2026, 10, 26))
        assert row["status"] == OperationStatusEnum.cancelled, name


@resp_mock.activate
def test_no_voyage_lines_keeps_ship_tag(db_session, marue_with_ports):
    """抜粋に便の行が1つも無い → 船のタグのまま（今まで）。"""
    company, ports = marue_with_ports
    down, _ = routes_of(db_session, company)
    mock_search(TODAY_SEARCHES)
    mock_kagoshima(kagoshima_html(naminoue=("欠航", "台風のため欠航いたします。")))

    _, _, departures = run_scraper(db_session, company.id)

    assert (
        find(departures, down, ports["鹿児島"], date(2026, 10, 1))["status"]
        == OperationStatusEnum.cancelled
    )


@resp_mock.activate
def test_midway_line_in_range_matches_current_voyage(db_session, marue_with_ports):
    """名瀬から書いた行（10/22）が、10/21 鹿児島発の今の便（10/22 19:00 着）に範囲で合う。"""
    company, ports = marue_with_ports
    down, _ = routes_of(db_session, company)
    searches = {
        **_voyage_searches(
            NAMINOUE,
            {KAGOSHIMA: "2026年10月21日 18:00"},
            NAHA,
            "2026年10月21日",
            "2026年10月22日 19:00",
        ),
        **_voyage_searches(
            NAMINOUE,
            {NAZE: "2026年10月22日 05:50"},
            NAHA,
            "2026年10月22日",
            "2026年10月22日 19:00",
        ),
    }

    _, _, departures, _ = run_1026(
        db_session,
        company.id,
        searches,
        now=datetime(2026, 10, 21, 8, 0),
        kagoshima=kagoshima_1026("■10月22日（木）名瀬発下り便…欠航", tags=["欠航"]),
    )

    assert (
        find(departures, down, ports["鹿児島"], date(2026, 10, 21))["status"]
        == OperationStatusEnum.cancelled
    )
    assert (
        find(departures, down, ports["名瀬"], date(2026, 10, 22))["status"]
        == OperationStatusEnum.cancelled
    )


@resp_mock.activate
def test_route_status_not_in_lines_before_departure_is_operating(
    db_session, marue_with_ports
):
    """航路単位：今日の始発港の便が出港前で、行が読めて合わない → operating。"""
    company, _ = marue_with_ports
    down, _ = routes_of(db_session, company)
    searches = _voyage_searches(
        NAMINOUE,
        {KAGOSHIMA: "2026年10月28日 18:00"},
        NAHA,
        "2026年10月28日",
        "2026年10月29日 19:00",
    )

    _, records, _, _ = run_1026(db_session, company.id, searches, now=NOW_1028)

    record = next(r for r in records if r["route_id"] == down.id)
    assert record["status"] == OperationStatusEnum.operating
    assert record["status_detail"] is None


@resp_mock.activate
def test_departed_voyage_uses_recorded_status(db_session, marue_with_ports):
    """出港後（行は合わず、タグは「欠航」が残る）：前回記録の operating のまま。記録が無ければ船のタグ。"""
    company, ports = marue_with_ports
    down, _ = routes_of(db_session, company)
    record_down_1029(db_session, down, ports, "鹿児島", date(2026, 10, 29), "operating")

    _, _, departures, logs = run_1026(
        db_session, company.id, down_1029_rows(), now=NOW_1029_EVE
    )

    for name, row in rows_1029(departures, down, ports).items():
        assert row["status"] == OperationStatusEnum.operating, name
    warning = next(log for log in logs if log["event"] == "voyage_not_in_excerpt")
    assert warning["assumed"] == "recorded"


@resp_mock.activate
def test_departed_voyage_without_record_falls_back_to_ship_tag(
    db_session, marue_with_ports
):
    company, ports = marue_with_ports
    down, _ = routes_of(db_session, company)

    _, _, departures, logs = run_1026(
        db_session, company.id, down_1029_rows(), now=NOW_1029_EVE
    )

    for name, row in rows_1029(departures, down, ports).items():
        assert row["status"] == OperationStatusEnum.cancelled, name
    warning = next(log for log in logs if log["event"] == "voyage_not_in_excerpt")
    assert warning["assumed"] == "ship_status"


@resp_mock.activate
def test_departed_voyage_keeps_per_port_recorded_status(db_session, marue_with_ports):
    """M2：港ごとに分かれていた状態（与論だけ delayed）は出港後も崩さない。"""
    company, ports = marue_with_ports
    down, _ = routes_of(db_session, company)
    record_down_1029(db_session, down, ports, "鹿児島", date(2026, 10, 29), "operating")
    for name in ["名瀬", "亀徳", "和泊", "本部"]:
        record_down_1029(db_session, down, ports, name, date(2026, 10, 30), "operating")
    record_down_1029(
        db_session,
        down,
        ports,
        "与論",
        date(2026, 10, 30),
        "delayed",
        "与論港は港変更の可能性があります。",
    )

    _, _, departures, _ = run_1026(
        db_session, company.id, down_1029_rows(), now=NOW_1029_EVE
    )

    rows = rows_1029(departures, down, ports)
    assert rows["与論"]["status"] == OperationStatusEnum.delayed
    assert rows["与論"]["status_detail"] == "与論港は港変更の可能性があります。"
    for name in ["鹿児島", "名瀬", "亀徳", "和泊", "本部"]:
        assert rows[name]["status"] == OperationStatusEnum.operating, name


@resp_mock.activate
def test_departed_is_decided_by_recorded_departure_when_search_fails(
    db_session, marue_with_ports
):
    """M3：始発港のキーの検索が失敗しても、記録した出港時刻で出港済みと分かる。"""
    company, ports = marue_with_ports
    down, _ = routes_of(db_session, company)
    record_down_1029(db_session, down, ports, "鹿児島", date(2026, 10, 29), "operating")
    searches = {
        **down_1029_rows(),
        (KAGOSHIMA, NAHA, "2026年10月29日"): search_html(None),
    }

    _, _, departures, logs = run_1026(
        db_session, company.id, searches, now=NOW_1029_EVE
    )

    for name in ["名瀬", "亀徳", "和泊", "与論", "本部"]:
        row = find(departures, down, ports[name], date(2026, 10, 30))
        assert row["status"] == OperationStatusEnum.operating, name
    warning = next(log for log in logs if log["event"] == "voyage_not_in_excerpt")
    assert warning["assumed"] == "recorded"


@resp_mock.activate
def test_route_status_departed_uses_recorded_status(db_session, marue_with_ports):
    """L5：航路単位も、出港済みで行が合わなければ記録のステータス。"""
    company, ports = marue_with_ports
    down, _ = routes_of(db_session, company)
    record_down_1029(
        db_session,
        down,
        ports,
        "鹿児島",
        date(2026, 10, 29),
        "delayed",
        "鹿児島新港の出港が遅れます。",
    )

    _, records, departures, _ = run_1026(
        db_session, company.id, down_1029_rows(), now=NOW_1029_EVE
    )

    record = next(r for r in records if r["route_id"] == down.id)
    assert record["status"] == OperationStatusEnum.delayed
    # 詳細は記録した行のもの。今の抜粋（他の便の「■10月27日…欠航」）は出さない
    assert record["status_detail"] == "鹿児島新港の出港が遅れます。"
    # 記録の無い港も、一番重い行のステータスと詳細
    row = find(departures, down, ports["名瀬"], date(2026, 10, 30))
    assert row["status"] == OperationStatusEnum.delayed
    assert row["status_detail"] == "鹿児島新港の出港が遅れます。"


@resp_mock.activate
def test_tag_heavier_than_lines_keeps_ship_tag(db_session, marue_with_ports):
    """安全装置：タグ（欠航）が読めた行の一番重いもの（条件付運航）より重い → 船のタグのまま。"""
    company, ports = marue_with_ports
    down, _ = routes_of(db_session, company)

    _, _, departures, logs = run_1026(
        db_session,
        company.id,
        down_1029_rows(),
        now=NOW_1028,
        kagoshima=kagoshima_1026(LINES_0_TO_2.format(first="条件付運航")),
    )

    for name, row in rows_1029(departures, down, ports).items():
        assert row["status"] == OperationStatusEnum.cancelled, name
    assert [log for log in logs if log["event"] == "voyage_tag_heavier_than_lines"]


@resp_mock.activate
def test_conditional_tag_without_conditional_line_keeps_ship_tag(
    db_session, marue_with_ports
):
    """安全装置：タグに条件付があるのに、条件付の行が無い → 船のタグのまま。"""
    company, ports = marue_with_ports
    down, _ = routes_of(db_session, company)

    _, _, departures, logs = run_1026(
        db_session,
        company.id,
        down_1029_rows(),
        now=NOW_1028,
        kagoshima=kagoshima_1026(
            "■10月27日（火）那覇港発上り便…欠航", tags=["欠航", "条件付運航"]
        ),
    )

    for name, row in rows_1029(departures, down, ports).items():
        assert row["status"] == OperationStatusEnum.cancelled, name
    assert [log for log in logs if log["event"] == "voyage_tag_heavier_than_lines"]


@resp_mock.activate
def test_unreadable_tag_does_not_become_operating(db_session, marue_with_ports):
    """タグが読めない船は、行が合わなくても operating にならず、抜港の行も作らない。"""
    company, ports = marue_with_ports
    down, _ = routes_of(db_session, company)
    # 亀徳の検索は0件 → 抜港の行を作るかどうかを _skipped_on_current_voyage() が調べる
    searches = down_1029_rows(ports_1030=(NAZE, WADOMARI, YORON, MOTOBU))

    _, _, departures, _ = run_1026(
        db_session,
        company.id,
        searches,
        now=NOW_1028,
        kagoshima=kagoshima_1026(tags=["読めない状態"]),
    )

    assert (
        find(departures, down, ports["鹿児島"], date(2026, 10, 29))["status"]
        == OperationStatusEnum.unknown
    )
    assert not [r for r in departures if r["status"] == OperationStatusEnum.skipped]


@resp_mock.activate
def test_vanished_voyage_line_is_searched_and_reset_to_scheduled(
    db_session, marue_with_ports
):
    """SC-005 の後半：便の行が消えた日付は、確認済みでも検索して運航予定に戻す。
    ship_name が空の行・skipped・operating の行しかないキーは、今までどおり間隔で飛ばす。"""
    company, ports = marue_with_ports
    down, up = routes_of(db_session, company)
    checked = NOW_1026 - timedelta(hours=1)
    # 船名つきの行：欠航は強制検索、skipped・operating は間隔どおり（飛ばす）
    specials = {
        (up.id, "那覇", date(2026, 10, 28)): "cancelled",
        (up.id, "本部", date(2026, 10, 29)): "skipped",
        (up.id, "与論", date(2026, 10, 28)): "operating",
    }
    for route, names in ((down, DOWN_PORT_NAMES), (up, UP_PORTS)):
        for name in names:
            for d in (date(2026, 10, 28), date(2026, 10, 29)):
                special = specials.get((route.id, name, d))
                db_session.add(
                    DepartureStatus(
                        route_id=route.id,
                        port_id=ports[name].id,
                        departure_date=d,
                        ship_name=NAMINOUE if special else "",
                        status=special or "no_service",
                        content_hash="x" * 64,
                        scraped_at=checked,
                        checked_at=checked,
                    )
                )
    db_session.commit()

    _, _, departures, _ = run_1026(
        db_session,
        company.id,
        {**down_1025_rows(), **up_1027_rows(), **UP_1028_ROWS},
        kagoshima=kagoshima_1026("■10月27日（火）那覇港発上り便…欠航"),
    )

    far = {c for c in search_calls() if c[2] in ("2026年10月28日", "2026年10月29日")}
    assert far == {(NAHA, KAGOSHIMA, "2026年10月28日")}
    row = find(departures, up, ports["那覇"], date(2026, 10, 28))
    assert row["status"] is None and row["status_detail"] is None


@resp_mock.activate
def test_departed_voyage_keeps_recorded_skipped_port(db_session, marue_with_ports):
    """PR #86 高：航行中に抜港の港が、検索結果が0件になっても「便なし」に変わらない（記録の skipped を保つ）。"""
    company, ports = marue_with_ports
    down, _ = routes_of(db_session, company)
    record_down_1029(db_session, down, ports, "鹿児島", date(2026, 10, 29), "operating")
    record_down_1029(
        db_session,
        down,
        ports,
        "与論",
        date(2026, 10, 30),
        "skipped",
        "与論港には寄港いたしません。",
        timeless=True,
    )
    searches = down_1029_rows(ports_1030=(NAZE, KAMETOKU, WADOMARI, MOTOBU))

    _, _, departures, _ = run_1026(db_session, company.id, searches, now=NOW_1029_EVE)

    row = find(departures, down, ports["与論"], date(2026, 10, 30))
    assert row["status"] == OperationStatusEnum.skipped
    assert row["status_detail"] == "与論港には寄港いたしません。"
    assert row["ship_name"] == NAMINOUE


@resp_mock.activate
def test_departed_voyage_with_heavier_tag_uses_tag_for_ports_not_yet_departed(
    db_session, marue_with_ports
):
    """PR #86 高：出港後でもタグが行より重ければ、まだ出港していない港はタグを優先する。出港済みの港は記録のまま。"""
    company, ports = marue_with_ports
    down, _ = routes_of(db_session, company)
    # 10/30 10:00 時点：名瀬（05:50）・亀徳（09:40）は出港済み。和泊（12:00）以降は未出港
    for name, d in (
        ("鹿児島", date(2026, 10, 29)),
        ("名瀬", date(2026, 10, 30)),
        ("亀徳", date(2026, 10, 30)),
    ):
        record_down_1029(db_session, down, ports, name, d, "operating")

    _, _, departures, logs = run_1026(
        db_session,
        company.id,
        down_1029_rows(),
        now=datetime(2026, 10, 30, 10, 0),
        kagoshima=kagoshima_1026(LINES_0_TO_2.format(first="条件付運航")),
    )

    d1030 = date(2026, 10, 30)
    for name in ["名瀬", "亀徳"]:
        assert (
            find(departures, down, ports[name], d1030)["status"]
            == OperationStatusEnum.operating
        ), name
    for name in ["和泊", "与論", "本部"]:
        assert (
            find(departures, down, ports[name], d1030)["status"]
            == OperationStatusEnum.cancelled
        ), name
    assert [log for log in logs if log["event"] == "voyage_tag_heavier_than_lines"]


@resp_mock.activate
def test_route_status_departed_with_heavier_tag_uses_tag(db_session, marue_with_ports):
    """航路単位も、出港後にタグが行より重ければタグ。"""
    company, ports = marue_with_ports
    down, _ = routes_of(db_session, company)
    record_down_1029(db_session, down, ports, "鹿児島", date(2026, 10, 29), "operating")

    _, records, _, _ = run_1026(
        db_session,
        company.id,
        down_1029_rows(),
        now=NOW_1029_EVE,
        kagoshima=kagoshima_1026(LINES_0_TO_2.format(first="条件付運航")),
    )

    assert (
        next(r for r in records if r["route_id"] == down.id)["status"]
        == OperationStatusEnum.cancelled
    )


def _seed_checked_far_rows(db_session, down, up, ports):
    """2〜3日先（10/28・10/29）の全キーに、1時間前に確認済みの行（便なし）を入れる。"""
    checked = NOW_1026 - timedelta(hours=1)
    for route, names in ((down, DOWN_PORT_NAMES), (up, UP_PORTS)):
        for name in names:
            for d in (date(2026, 10, 28), date(2026, 10, 29)):
                db_session.add(
                    DepartureStatus(
                        route_id=route.id,
                        port_id=ports[name].id,
                        departure_date=d,
                        ship_name="",
                        status="no_service",
                        content_hash="x" * 64,
                        scraped_at=checked,
                        checked_at=checked,
                    )
                )
    db_session.commit()


def _far_up_keys(*days: str) -> set[tuple[str, str, str]]:
    return {
        (code, KAGOSHIMA, day)
        for day in days
        for code in (NAHA, MOTOBU, YORON, WADOMARI, KAMETOKU, NAZE)
    }


@pytest.mark.parametrize(
    "line, expected_days",
    [
        # 始発港の行は、その日のキーだけ（前日の存在しない便は検索しない）
        ("■10月29日（水）那覇港発上り便…欠航", ("2026年10月29日",)),
        # 途中の港から書いた行は、始発が前日のこともあるので前日も検索する
        ("■10月29日（水）名瀬発上り便…欠航", ("2026年10月28日", "2026年10月29日")),
    ],
)
@resp_mock.activate
def test_previous_day_is_searched_only_for_lines_from_midway(
    db_session, marue_with_ports, line, expected_days
):
    company, ports = marue_with_ports
    down, up = routes_of(db_session, company)
    _seed_checked_far_rows(db_session, down, up, ports)

    run_1026(
        db_session,
        company.id,
        up_1027_rows(),
        kagoshima=kagoshima_1026(line),
    )

    far = {c for c in search_calls() if c[2] in ("2026年10月28日", "2026年10月29日")}
    assert far == _far_up_keys(*expected_days)


# ---------------------------------------------------------------------------
# 臨時便の読み取り（12-marue-extra-voyages。_parse_extra_voyages）
# ---------------------------------------------------------------------------

NAMINOUE = "フェリー波之上"


def naminoue_detail(*replacements: tuple[str, str]) -> str:
    html = read_fixture("marue/ship_detail_naminoue_20261026.html")
    for old, new in replacements:
        assert old in html, old
        html = html.replace(old, new)
    return html


def parse_extra(db_session, company_id, html, now: datetime = NOW_1026):
    scraper = MarueFerry(db_session, company_id)
    with structlog.testing.capture_logs() as logs, fixed_now(now):
        parsed = scraper._parse_extra_voyages(html, NAMINOUE)
    return scraper, parsed, logs


def stop_times(voyage):
    return [
        (
            s.arrival_at.strftime("%m-%d %H:%M") if s.arrival_at else None,
            s.departure_at.strftime("%m-%d %H:%M") if s.departure_at else None,
        )
        for s in voyage.stops
    ]


def test_extra_voyages_are_read_from_detail_page(db_session, marue_with_ports):
    company, ports = marue_with_ports
    scraper, parsed, logs = parse_extra(db_session, company.id, naminoue_detail())

    assert parsed.complete is True
    down, up = parsed.voyages
    assert [v.ship_name for v in parsed.voyages] == [NAMINOUE, NAMINOUE]
    assert stop_times(down) == [
        (None, "10-26 16:00"),
        ("10-27 03:00", "10-27 03:50"),
        ("10-27 11:30", "10-27 12:00"),
        ("10-27 13:50", None),
    ]
    assert stop_times(up) == [
        (None, "10-28 05:00"),
        ("10-28 07:00", "10-28 07:20"),
        ("10-28 09:50", "10-28 10:10"),
        ("10-28 12:10", "10-28 12:40"),
        ("10-28 14:30", "10-28 15:00"),
        ("10-28 18:30", "10-28 19:20"),
        ("10-29 07:30", None),
    ]
    assert down.skip_note == (
        "※ 亀徳港(徳之島)、和泊港(沖永良部島)、与論港(与論島)には寄港いたしません。"
    )
    assert up.skip_note is None
    routes = scraper._route_directions()
    assert routes[down.route_id] == "下り" and routes[up.route_id] == "上り"
    # 【欠航】の「9月27日(火)」は臨時便ではないので警告も出ない
    assert not [log for log in logs if log["log_level"] == "warning"]


def test_extra_voyages_none_for_plain_page(db_session, marue_with_ports):
    company, _ = marue_with_ports
    _, parsed, logs = parse_extra(
        db_session, company.id, read_fixture("marue/ship_detail_normal.html")
    )
    assert parsed.voyages == () and parsed.complete is True
    assert not [log for log in logs if log["log_level"] == "warning"]


def test_extra_voyages_none_without_archive(db_session, marue_with_ports):
    company, _ = marue_with_ports
    assert parse_extra(db_session, company.id, "<html><body>x</body></html>")[1] is None
    assert parse_extra(db_session, company.id, None)[1] is None


@pytest.mark.parametrize(
    "replacements",
    [
        # 曜日違い
        [("10月28日(水)那覇港", "10月28日(木)那覇港")],
        # 航路に無い港
        [("10月28日(水)与論港", "10月28日(水)伊延港")],
        # 順番違い（本部と与論を入れ替え）
        [
            ("10月28日(水)本部港　07:00(入港)/07:20(出港)", "@@"),
            (
                "10月28日(水)与論港　09:50(入港)/10:10(出港)",
                "10月28日(水)本部港　07:00(入港)/07:20(出港)",
            ),
            ("@@", "10月28日(水)与論港　09:50(入港)/10:10(出港)"),
        ],
        # 途中の港で出港なし
        [
            (
                "10月28日(水)本部港　07:00(入港)/07:20(出港)",
                "10月28日(水)本部港　07:00(入港)",
            )
        ],
        # 終点の入港なし
        [("<p>10月29日(木)鹿児島新港　07:30(入港)</p>", "")],
        # 時刻が前の港より前
        [
            (
                "10月28日(水)本部港　07:00(入港)/07:20(出港)",
                "10月28日(水)本部港　04:00(入港)/04:20(出港)",
            )
        ],
        # 知らない形の行
        [
            (
                "10月28日(水)亀徳港　14:30(入港)/15:00(出港)",
                "10月28日(水)亀徳港　14:30ごろ",
            )
        ],
    ],
)
def test_unreadable_extra_voyage_is_dropped_with_warning(
    db_session, marue_with_ports, replacements
):
    company, _ = marue_with_ports
    _, parsed, logs = parse_extra(
        db_session, company.id, naminoue_detail(*replacements)
    )

    # 読めた下りだけが入り、complete は False（消さない）
    assert parsed.complete is False
    assert len(parsed.voyages) == 1
    assert stop_times(parsed.voyages[0])[0] == (None, "10-26 16:00")
    warnings = [log for log in logs if log["event"] == "extra_voyage_unreadable"]
    assert len(warnings) == 1
    assert warnings[0]["ship"] == NAMINOUE
    assert "上り" in warnings[0]["heading"]


@pytest.mark.parametrize("left,right", [("(", ")"), ("（", "）")])
def test_extra_heading_accepts_both_parentheses(
    db_session, marue_with_ports, left, right
):
    company, _ = marue_with_ports
    html = naminoue_detail(
        ("【臨時便(下り)】", f"【臨時便{left}下り{right}】"),
        ("【臨時便(上り)】", f"【臨時便{left}上り{right}】"),
    )
    _, parsed, _ = parse_extra(db_session, company.id, html)
    assert len(parsed.voyages) == 2


def test_two_extra_voyages_in_same_direction(db_session, marue_with_ports):
    company, _ = marue_with_ports
    second = (
        "<p>【臨時便(下り)】</p>"
        "<p>10月27日(火)鹿児島新港　16:00(出港)</p>"
        "<p>10月28日(水)名瀬港　03:00(入港)/03:50(出港)</p>"
        "<p>10月28日(水)那覇港　13:50(入港)</p>"
    )
    html = naminoue_detail(
        ("<p>【臨時便(上り)】</p>", second + "<p>【臨時便(上り)】</p>")
    )
    _, parsed, _ = parse_extra(db_session, company.id, html)
    assert len(parsed.voyages) == 3
    assert [stop_times(v)[0][1] for v in parsed.voyages[:2]] == [
        "10-26 16:00",
        "10-27 16:00",
    ]


def test_extra_year_rolls_over_new_year(db_session, marue_with_ports):
    company, _ = marue_with_ports
    html = naminoue_detail(
        ("10月26日(月)鹿児島新港", "1月2日(土)鹿児島新港"),
        ("10月27日(火)", "1月3日(日)"),
    )
    _, parsed, _ = parse_extra(
        db_session, company.id, html, now=datetime(2026, 12, 30, 10, 0)
    )
    down = parsed.voyages[0]
    assert down.stops[0].departure_at == datetime(2027, 1, 2, 16, 0)
    assert down.stops[-1].arrival_at == datetime(2027, 1, 3, 13, 50)
