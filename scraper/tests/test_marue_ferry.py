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

    with patch("scraper.scrapers.marue_ferry.date", _Date), patch(
        "scraper.scrapers.marue_ferry.datetime", _DateTime
    ), patch("scraper.scrapers.base.datetime", _DateTime):
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
def test_skip_port_is_cancelled_only_there(db_session, marue_with_ports):
    """抜港 → その港だけ cancelled、他は船ステータス（US4 シナリオ3）。"""
    company, ports = marue_with_ports
    departures, _ = run_with_ships(
        db_session, company, ("通常運航", "本日、与論港は抜港となります。")
    )

    rows = down_statuses(db_session, company, ports, departures)
    assert rows["与論"]["status"] == OperationStatusEnum.cancelled
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
        == OperationStatusEnum.cancelled
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
