"""
MarueFerry (マルエーフェリー) scraper.

処理の流れ（specs/4-departure-port-status research R3・R8・R9・R10）:
  1. 船ステータス: GET https://www.aline-ferry.com/kagoshima/
     a > div.route-head > div.ferry-name / div.tag-list span / div.situation-excerpt、a[href] が船別詳細ページ
     便検索より先に読む（抜粋の便の行から、2日先以降で検索する日付を決めるため）
  2. 便検索: POST https://www.aline-ferry.com/search/result.php
     startDate=YYYY年MM月DD日, startPort=<出発港コード>, endPort=<到着港コード>
     ※ startDate は必ず「YYYY年MM月DD日」形式で送る。ISO 形式（YYYY-MM-DD）だと日付に関係なく
       常に「※下記参照 / マリックスライン㈱」が返る（以前の不具合の原因）
     - 方向 × 終点以外の寄港地 × 日付（今日〜MARUE_SEARCH_DAYS_AHEAD 日先）で検索する
     - 今日・明日は毎回、2日先以降は検索キーごとに MARUE_FAR_SEARCH_INTERVAL_HOURS たったら検索する。
       ただし抜粋に便の行がある日付と、前回に船名つきで状態（欠航・運休・条件付・通常運航）を付けた日付は、
       間隔に関係なく毎回検索する（公式の発表をすぐ反映し、行が消えたらすぐ運航予定に戻すため）
     - 検索の間に MARUE_SEARCH_DELAY_SECONDS 待つ
  3. 船別詳細ページ: 各船の a[href] を GET（港別情報の抽出に使う）

検索結果（table.s-result tbody tr）:
    <td>鹿児島航路</td><td>フェリーあけぼの</td><td>2026年10月4日 05:50</td><td>2026年10月4日 19:00</td>
    <td>352km</td><td>マルエーフェリー</td>
    - 乗船日時 = その港の出港日時、下船日時 = 到着港への到着日時
    - 他社運航の日は 船名「※下記参照」・会社名「マリックスライン㈱」・日時「－」

航路単位（parse）:
    今日の始発港（下り＝鹿児島、上り＝那覇）の検索結果で方向ごとに判定する
    - マルエーの行がある → その船の船ステータス（船名で対応付け。無ければ unknown）
    - 他社運航のみ・0件 → no_service
    - 検索に失敗 → 安全側として船ステータスのうち一番重いもの（warning）

港別（parse_departures）:
    検索結果ごとに行を作る
    - 0件 → no_service
    - 他社運航 → no_service + operated_by_company_id（マリックスライン）
    - マルエーの船 → 便を (船名, 航路, 下船日時) で特定し、船ごとに「まだ着いていない一番早い便」（今の便）の行に
      船ステータス（＋港別情報）を入れる。それより後の便は、抜粋にその便の行があればその状態を全港に入れ
      （港別情報は使わない）、無ければ status=None（運航予定）
    港別情報（FR-006、utils/port_notice.py）:
    - 船ステータスが欠航・運休・便なし → 全港そのまま
    - 抜粋と船別詳細ページの本文から、言及された港を 抜港（寄港いたしません等）→ skipped、港変更・条件付 → delayed にする
    - 「臨時便運航」は operating として読む（運休・条件付などの語があればそちらが先）
    - 船ブロックのタグは全部読む（一番重いものが船のステータス。条件付・スケジュール変更かどうかは別に持つ）
    - タグは船の全便ぶんをまとめたもの（「■10月20日(火)那覇発上り便…条件付き運航」「■10月21日(水)鹿児島新港発
      下り便…欠航」のように便ごとの状態が抜粋に並ぶ）。抜粋に便が2つ以上あり、その便（始発港の出港日・上り/下り）の
      行があれば、船のステータスの代わりにその行の状態を使う（航路単位も同じ）。行が無ければ船のステータスのまま（安全側）
    - 便と行の照合は出港日の一致が先。途中の港から書いた行（「名瀬発下り便」）だけ、出港日〜下船日の範囲でも合わせる
    - 抜粋に便の行があるのに今の便に合う行が無いとき（公式は変更のある便に行を書く）:
      出港前なら operating（港別情報は当てない）。ただしタグのほうが行より重い・条件付の行が無いなど、
      行の無い便の変更かもしれないときは船のタグのまま（voyage_tag_heavier_than_lines）。
      出港済みなら、公式は過ぎた便の行を消すので、前回記録したその港のステータスに戻す
    - 船が条件付だけ（スケジュール変更・遅延のタグが無い）で港別情報がある → 言及の無い港は operating。
      港別情報が無い → 全港 delayed（port_notice_unmatched）。
      スケジュール変更・遅延のタグもある船は言及の無い港も船のステータスのまま（時刻が変わっているため）
    - 抜港の港の検索結果に日時が無い（「－」）・0件でも、今の便がその港を抜港とする日なら
      skipped（時刻なし）の行を作る。「便なし」や行の欠落にしない
    - skipped は港の行だけ。航路単位（operation_statuses）には書かない
    すべて freeze_after_departure=True（出港済みの行は確定）、replace_scope=(route, port, date)

raw_html_hash: 鹿児島航路ページの HTML ＋ 今日の始発港2つの検索結果を正規化した文字列
valid_date: 常に date.today()
"""

import json
import re
import time
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup
from sqlalchemy import func, select

from scraper.config import settings
from scraper.db.models import (
    DepartureStatus,
    FerryCompany,
    OperationStatusEnum,
    PortCompanyCode,
    Route,
    RouteStop,
)
from scraper.scrapers.base import BaseScraper
from scraper.utils.port_notice import (
    PortNotice,
    extract_notice_text,
    extract_port_notices,
)
from scraper.utils.ports import PortResolver

SEARCH_URL = "https://www.aline-ferry.com/search/result.php"
KAGOSHIMA_URL = "https://www.aline-ferry.com/kagoshima/"

# 船ステータスの重さ（検索に失敗したときの安全側の判定に使う）
_SEVERITY = {
    OperationStatusEnum.cancelled: 4,
    OperationStatusEnum.suspended: 3,
    OperationStatusEnum.delayed: 2,
    OperationStatusEnum.operating: 1,
}

# 条件付（delayed）として読むタグ・便の行の語。「寄港地変更」は「港変更」を含まない（寄・港・地・変・更）
_CONDITIONAL_WORDS = ("条件付", "港変更", "寄港地変更", "抜港")


@dataclass(frozen=True)
class SearchRow:
    """便検索の結果1行。"""

    ship_name: str
    company_name: str
    is_other_company: bool
    departure_at: datetime | None
    arrival_at: datetime | None


@dataclass(frozen=True)
class VoyageStatus:
    """抜粋の便ごとの行（「■10月20日(火)那覇発上り便…条件付き運航・寄港地変更」）。"""

    departure_date: date  # 始発港の出港日
    direction: str  # 「上り」「下り」
    status: OperationStatusEnum
    conditional: bool
    schedule_changed: bool
    # 途中の港から書いた行（「■10月22日(木)名瀬発下り便…」）か。この行だけ出港日〜到着日の範囲で照合する（R7）
    from_midway: bool = False


@dataclass(frozen=True)
class ShipInfo:
    """鹿児島航路ページの船ブロック1つ。status は判定できなければ None。"""

    name: str
    status: OperationStatusEnum | None
    excerpt: str | None
    detail_url: str | None
    # どれかのタグが「条件付」か。遅延・スケジュール変更も status は delayed になるので区別する（FR-006）
    conditional: bool = False
    # どれかのタグが「遅延」「スケジュール変更」か（言及の無い港も時刻が変わっている）
    schedule_changed: bool = False
    # 抜粋の便ごとの状態（書き方が違って読めなければ空）
    voyages: tuple[VoyageStatus, ...] = ()
    # 今の便に合う行が無く、出港前なので通常運航とみなした（FR-011）。港別情報は当てない
    assumed_operating: bool = False
    # 今の便に合う行が無く、出港済みなので前回記録したステータスに戻す（R7）。港別情報は当てない
    use_recorded: bool = False
    # use_recorded のうち、タグのほうが行より重い（行の無い便の変更かもしれない）。
    # まだ出港していない港は記録でなくタグ＋港別情報で決める
    tag_over_recorded: bool = False


@dataclass(frozen=True)
class RecordedVoyage:
    """前回までに記録した、ある便の行（departure_statuses）。"""

    # (port_id, 出港日) → (status, status_detail)。status が NULL の行（運航予定）は入れない
    ports: dict[tuple[int, date], tuple[OperationStatusEnum, str | None]]
    # 記録した出港時刻（始発港の検索が失敗した回でも出港済みか分かるように）
    departures: tuple[datetime, ...]
    # skipped・unknown を除いた、一番重いステータス
    worst: OperationStatusEnum | None
    # worst を取った行の status_detail（今の抜粋は他の便の話なので使わない）
    worst_detail: str | None = None


class MarueFerry(BaseScraper):
    def __init__(self, session, company_id: int) -> None:
        # 便検索の POST は読み取り専用の検索（副作用なし）なので、429/5xx でリトライする
        super().__init__(session, company_id, retry_post=True)
        self._search_count = 0

    # ------------------------------------------------------------------
    # fetch
    # ------------------------------------------------------------------

    def fetch(self) -> str:
        self._valid_date = date.today()
        self._searches: dict[tuple[int, int, date], list[SearchRow] | None] = {}
        self._search_count = 0
        self._recorded_cache: dict[tuple[str, int, datetime], RecordedVoyage] = {}

        routes = [r for r in self._load_routes() if r]
        self._stops = self._load_stops(routes)
        self._resolver = PortResolver.from_session(self.session)
        codes = self._load_port_codes()
        now = datetime.now()

        # 船ステータス（鹿児島航路ページ）。便の行から 2日先以降の検索キーを決めるので、便検索より先に読む
        resp = self.http.get(KAGOSHIMA_URL, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        self._ships = self._parse_ships(resp.text)
        self._voyage_cache: dict[tuple[str, int, date, datetime | None], ShipInfo] = {}
        forced = self._voyage_search_keys(routes) | self._recorded_search_keys(routes)

        for offset in range(settings.marue_search_days_ahead + 1):
            d = self._valid_date + timedelta(days=offset)
            for route in routes:
                stops = self._stops.get(route.id, [])
                if len(stops) < 2:
                    if offset == 0:
                        self._log.warning("route_stops_missing", route_id=route.id)
                    continue
                end_code = codes.get(stops[-1].port_id)
                for stop in stops[:-1]:
                    key = (route.id, stop.port_id, d)
                    if (
                        offset >= 2
                        and key not in forced
                        and not self._needs_far_search(key, now)
                    ):
                        continue
                    start_code = codes.get(stop.port_id)
                    if start_code is None or end_code is None:
                        self._log.warning(
                            "port_code_missing", route_id=route.id, port_id=stop.port_id
                        )
                        continue
                    self._searches[key] = self._search(start_code, end_code, d)

        # 船別詳細ページ（港別情報の抽出用。失敗しても続ける）
        self._ship_details: dict[str, str | None] = {}
        for ship in self._ships.values():
            if not ship.detail_url:
                continue
            try:
                detail = self.http.get(ship.detail_url, timeout=30)
                detail.raise_for_status()
                detail.encoding = detail.apparent_encoding
                self._ship_details[ship.name] = detail.text
            except Exception as exc:
                self._log.warning(
                    "ship_detail_fetch_failed", ship=ship.name, error=str(exc)
                )
                self._ship_details[ship.name] = None

        # 方向ごとの便有無が変わったら raw_html_hash も変わるように、今日の始発港の検索結果をつなげる
        return (
            resp.text
            + "\n<!-- searches: "
            + self._normalized_origin_searches(routes)
            + " -->"
        )

    def _voyage_search_keys(self, routes: list[Route]) -> set[tuple[int, int, date]]:
        """抜粋の便の行から決まる、2日先以降の検索キー（間隔に関係なく検索する。R5）。

        途中の港から書いた行は始発の出港日が1日前のこともあるので、行の日付と前日の両方を始発の出港日とみなす。
        """
        directions = self._route_directions()
        first = self._valid_date + timedelta(days=2)
        last = self._valid_date + timedelta(days=settings.marue_search_days_ahead)
        keys: set[tuple[int, int, date]] = set()
        for ship in self._ships.values():
            for voyage in ship.voyages:
                route = next(
                    (r for r in routes if directions.get(r.id) == voyage.direction),
                    None,
                )
                stops = self._stops.get(route.id, []) if route else []
                if route is None or len(stops) < 2:
                    continue
                for start in (
                    voyage.departure_date,
                    voyage.departure_date - timedelta(days=1),
                ):
                    for stop in stops[:-1]:
                        d = start + timedelta(
                            days=stop.day_offset - stops[0].day_offset
                        )
                        if first <= d <= last:
                            keys.add((route.id, stop.port_id, d))
        return keys

    def _recorded_search_keys(self, routes: list[Route]) -> set[tuple[int, int, date]]:
        """前回に状態を付けた 2日先以降のキーも、間隔に関係なく検索する（便の行が消えたとき。R5）。

        ship_name が空の行（他社運航・0件）と skipped・NULL の行は含めない。含めると間隔がほぼ効かなくなる。
        """
        if not routes:
            return set()
        today = self._valid_date
        rows = self.session.execute(
            select(
                DepartureStatus.route_id,
                DepartureStatus.port_id,
                DepartureStatus.departure_date,
            )
            .where(
                DepartureStatus.route_id.in_([r.id for r in routes]),
                DepartureStatus.ship_name != "",
                DepartureStatus.status.in_(
                    [
                        s.value
                        for s in (
                            OperationStatusEnum.cancelled,
                            OperationStatusEnum.suspended,
                            OperationStatusEnum.delayed,
                            OperationStatusEnum.operating,
                        )
                    ]
                ),
                DepartureStatus.departure_date >= today + timedelta(days=2),
                DepartureStatus.departure_date
                <= today + timedelta(days=settings.marue_search_days_ahead),
            )
            .distinct()
        ).all()
        return {(r.route_id, r.port_id, r.departure_date) for r in rows}

    def _needs_far_search(self, key: tuple[int, int, date], now: datetime) -> bool:
        """2日先以降の検索キー：行が無いか、最後の確認から MARUE_FAR_SEARCH_INTERVAL_HOURS たっていれば検索する。"""
        route_id, port_id, d = key
        last_checked = self.session.execute(
            select(func.max(DepartureStatus.checked_at)).where(
                DepartureStatus.route_id == route_id,
                DepartureStatus.port_id == port_id,
                DepartureStatus.departure_date == d,
            )
        ).scalar()
        if last_checked is None:
            return True
        return last_checked < now - timedelta(
            hours=settings.marue_far_search_interval_hours
        )

    def _normalized_origin_searches(self, routes: list[Route]) -> str:
        result = {}
        for route in routes:
            stops = self._stops.get(route.id, [])
            if not stops:
                continue
            rows = self._searches.get((route.id, stops[0].port_id, self._valid_date))
            result[str(route.id)] = (
                None
                if rows is None
                else [
                    [
                        r.ship_name,
                        r.company_name,
                        _iso(r.departure_at),
                        _iso(r.arrival_at),
                    ]
                    for r in rows
                ]
            )
        return json.dumps(result, ensure_ascii=False, sort_keys=True)

    # ------------------------------------------------------------------
    # 便検索
    # ------------------------------------------------------------------

    @staticmethod
    def _format_search_date(d: date) -> str:
        return f"{d.year}年{d.month:02d}月{d.day:02d}日"

    def _search(
        self, start_code: str, end_code: str, d: date
    ) -> list[SearchRow] | None:
        """便検索。None = 取得・解析の失敗、[] = 便0件。"""
        if self._search_count > 0:
            time.sleep(settings.marue_search_delay_seconds)
        self._search_count += 1

        try:
            resp = self.http.post(
                SEARCH_URL,
                data={
                    "startDate": self._format_search_date(d),
                    "startPort": start_code,
                    "endPort": end_code,
                },
                timeout=30,
            )
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding
        except Exception as exc:
            self._log.warning(
                "search_failed",
                start=start_code,
                end=end_code,
                date=str(d),
                error=str(exc),
            )
            return None

        table = BeautifulSoup(resp.text, "lxml").select_one("table.s-result")
        if table is None:
            self._log.warning(
                "result_table_missing", start=start_code, end=end_code, date=str(d)
            )
            return None

        rows: list[SearchRow] = []
        for tr in table.select("tbody tr"):
            tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if len(tds) < 6:
                self._log.warning("search_row_unknown", cells=len(tds), date=str(d))
                return None
            ship_name, dep_text, arr_text, company_name = tds[1], tds[2], tds[3], tds[5]
            is_other = "マルエー" not in company_name
            departure_at = _parse_search_datetime(dep_text)
            arrival_at = _parse_search_datetime(arr_text)
            if not is_other and (departure_at is None or arrival_at is None):
                # 日時が読めない行も残す。抜港の港なら parse_departures() が skipped の行にする
                self._log.warning(
                    "search_datetime_missing",
                    dep=dep_text,
                    arr=arr_text,
                    date=str(d),
                )
                departure_at = arrival_at = None
            rows.append(
                SearchRow(ship_name, company_name, is_other, departure_at, arrival_at)
            )
        return rows

    # ------------------------------------------------------------------
    # 航路単位（operation_statuses）
    # ------------------------------------------------------------------

    def parse(self, html: str) -> list[dict]:
        down_route, up_route = self._load_routes()
        if down_route is None:
            self._log.warning("route_not_found", direction="down")
        if up_route is None:
            self._log.warning("route_not_found", direction="up")
        valid_date = getattr(self, "_valid_date", date.today())
        ships = getattr(self, "_ships", None)
        if ships is None:
            ships = self._parse_ships(html)

        records: list[dict] = []
        for route in [r for r in (down_route, up_route) if r]:
            status, detail, source_url = self._route_status(route, ships, valid_date)
            records.append(
                {
                    "route_id": route.id,
                    "status": status,
                    "status_detail": detail,
                    "valid_date": valid_date,
                    "scraped_at": datetime.now(),
                    "source_url": source_url,
                }
            )

        self._log.info("parsed", records=len(records))
        return records

    def _route_status(
        self, route: Route, ships: dict[str, ShipInfo], valid_date: date
    ) -> tuple[OperationStatusEnum, str | None, str]:
        """(status, status_detail, source_url)。今日の始発港の検索結果で方向ごとに判定する（research R10）。"""
        stops = getattr(self, "_stops", {}).get(route.id, [])
        rows = None
        if stops:
            rows = getattr(self, "_searches", {}).get(
                (route.id, stops[0].port_id, valid_date)
            )

        if rows is None:
            # 検索に失敗 → 今までの安全側の挙動（船ステータスのうち一番重いもの）
            self._log.warning("origin_search_unavailable", route_id=route.id)
            return (*self._worst_ship_status(ships), KAGOSHIMA_URL)

        marue_rows = [r for r in rows if not r.is_other_company]
        if not marue_rows:
            return OperationStatusEnum.no_service, None, SEARCH_URL

        self._require_ship_statuses(ships)
        ship = ships.get(marue_rows[0].ship_name)
        if ship is None or ship.status is None:
            self._log.warning(
                "ship_not_found", ship=marue_rows[0].ship_name, route_id=route.id
            )
            return OperationStatusEnum.unknown, None, KAGOSHIMA_URL
        original = ship
        ship = self._for_voyage(ship, route.id, valid_date, marue_rows[0].arrival_at)
        if ship.tag_over_recorded:
            ship = original
        elif ship.use_recorded and marue_rows[0].arrival_at is not None:
            recorded = self._recorded_voyage(
                ship.name, route.id, marue_rows[0].arrival_at
            )
            return ship.status, recorded.worst_detail, KAGOSHIMA_URL
        return ship.status, self._ship_detail_text(ship), KAGOSHIMA_URL

    def _worst_ship_status(
        self, ships: dict[str, ShipInfo]
    ) -> tuple[OperationStatusEnum, str | None]:
        self._require_ship_statuses(ships)
        known = [s for s in ships.values() if s.status is not None]
        if len({s.status for s in known}) > 1:
            self._log.warning(
                "mixed_ship_statuses", statuses=sorted({s.status.value for s in known})
            )
        worst = max(known, key=lambda s: _SEVERITY.get(s.status, 0))
        return worst.status, self._ship_detail_text(worst)

    def _require_ship_statuses(self, ships: dict[str, ShipInfo]) -> None:
        if not any(s.status is not None for s in ships.values()):
            self._log.error("no_records_parsed")
            raise RuntimeError(
                "MarueFerry.parse: no ship statuses parsed (possible site structure change)"
            )

    @staticmethod
    def _ship_detail_text(ship: ShipInfo) -> str | None:
        if ship.status == OperationStatusEnum.operating:
            return None
        return ship.excerpt or None

    # ------------------------------------------------------------------
    # 港別（departure_statuses）
    # ------------------------------------------------------------------

    def parse_departures(self) -> list[dict]:
        searches = getattr(self, "_searches", None)
        if not searches:
            return []
        ships = getattr(self, "_ships", {})
        marix_id = self._marix_company_id()
        now = datetime.now()
        self._get_resolver()
        self._notices: dict[str, list[PortNotice]] = {}

        # 船ごとに「まだ着いていない一番早い便」(route_id, arrival_at) を決める（research R9）
        # 候補は今回の検索結果と、前回までに記録した行（DB）。上りの便は始発日の途中港を全部出てから
        # 翌朝に鹿児島へ着くので、日付が変わってから着くまでの間は、走っている便が今日以降の検索結果に
        # 出てこない。DB の行も見ないと、船ステータスが次の便に付いてしまう。
        # ただし検索に出てくる便は検索の時刻を正とする（出港済みの行は確定していて、遅延前の時刻のまま残るため）
        candidates: list[tuple[str, int, datetime]] = [
            (row.ship_name, route_id, row.arrival_at)
            for (route_id, _, _), rows in searches.items()
            for row in rows or []
            if not row.is_other_company and row.arrival_at is not None
        ]
        candidates.extend(self._recorded_voyages(now, candidates))
        current_voyage: dict[str, tuple[int, datetime]] = {}
        for ship_name, route_id, arrival_at in candidates:
            if arrival_at <= now:
                continue
            cur = current_voyage.get(ship_name)
            if cur is None or arrival_at < cur[1]:
                current_voyage[ship_name] = (route_id, arrival_at)
        self._current_voyage = current_voyage

        records: list[dict] = []
        for (route_id, port_id, d), rows in searches.items():
            if rows is None:
                continue  # 失敗したキーは書かない（次の実行で取り直す）
            base = {
                "route_id": route_id,
                "port_id": port_id,
                "departure_date": d,
                "source_url": SEARCH_URL,
                "freeze_after_departure": True,
                "replace_scope": (route_id, port_id, d),
            }
            marue_rows = [r for r in rows if not r.is_other_company]
            if not marue_rows:
                skipped = self._skipped_on_any_current_voyage(route_id, port_id, d)
                if skipped is not None:
                    records.append(self._skipped_record(base, *skipped))
                    continue
                other = next((r for r in rows if r.is_other_company), None)
                records.append(
                    {
                        **base,
                        "ship_name": "",
                        "status": OperationStatusEnum.no_service,
                        "status_detail": None,
                        "scheduled_departure_at": None,
                        "scheduled_arrival_at": None,
                        "operated_by_company_id": (
                            marix_id
                            if other is not None and "マリックス" in other.company_name
                            else None
                        ),
                    }
                )
                continue

            seen_ships: set[str] = set()
            for row in marue_rows:
                if row.ship_name in seen_ships:
                    self._log.warning(
                        "search_duplicate_ship", ship=row.ship_name, date=str(d)
                    )
                    continue
                seen_ships.add(row.ship_name)
                if row.arrival_at is None:
                    detail = self._skipped_on_current_voyage(
                        row.ship_name, route_id, port_id, d
                    )
                    if detail is None:
                        self._log.warning(
                            "search_row_without_datetime_skipped",
                            ship=row.ship_name,
                            route_id=route_id,
                            port_id=port_id,
                            date=str(d),
                        )
                    else:
                        records.append(
                            self._skipped_record(base, row.ship_name, detail)
                        )
                    continue
                if current_voyage.get(row.ship_name) == (route_id, row.arrival_at):
                    status, detail = self._current_voyage_status(
                        row.ship_name, ships, route_id, port_id, d, row.departure_at
                    )
                else:
                    status, detail = self._future_voyage_status(
                        row.ship_name, ships, route_id, row
                    )
                records.append(
                    {
                        **base,
                        "ship_name": row.ship_name,
                        "status": status,
                        "status_detail": detail,
                        "scheduled_departure_at": row.departure_at,
                        "scheduled_arrival_at": row.arrival_at,
                        "operated_by_company_id": None,
                    }
                )

        self._log.info("parsed_departures", records=len(records))
        return records

    @staticmethod
    def _skipped_record(base: dict, ship_name: str, detail: str) -> dict:
        """時刻なしの抜港の行。"""
        return {
            **base,
            "ship_name": ship_name,
            "status": OperationStatusEnum.skipped,
            "status_detail": detail,
            "scheduled_departure_at": None,
            "scheduled_arrival_at": None,
            "operated_by_company_id": None,
        }

    def _skipped_on_any_current_voyage(
        self, route_id: int, port_id: int, d: date
    ) -> tuple[str, str] | None:
        """今の便のどれかが、この航路のこの港をこの日に抜港とするなら (船名, 告知の文)。"""
        for ship_name in sorted(self._current_voyage):
            detail = self._skipped_on_current_voyage(ship_name, route_id, port_id, d)
            if detail is not None:
                return ship_name, detail
        return None

    def _skipped_on_current_voyage(
        self, ship_name: str, route_id: int, port_id: int, d: date
    ) -> str | None:
        """その船の今の便が同じ航路にあり、その港が抜港で、出港日が d なら告知の文（無ければ None）。

        出港日 ＝ 今の便の下船日 −（終点の day_offset − その港の day_offset）
        """
        cur = self._current_voyage.get(ship_name)
        if cur is None or cur[0] != route_id:
            return None
        ship = getattr(self, "_ships", {}).get(ship_name)
        if ship is not None:
            ship = self._for_current_voyage(ship)
        if ship is not None and ship.use_recorded:
            # 港別情報は見ない。航行中の抜港は、前回その港に付けた skipped をそのまま保つ
            status, detail = self._recorded_voyage(
                ship_name, route_id, cur[1]
            ).ports.get((port_id, d), (None, None))
            if status == OperationStatusEnum.skipped and detail:
                return detail
            if not ship.tag_over_recorded:
                return None  # 港別情報は見ない
            ship = self._ships[ship_name]  # タグのほうが重い。タグ＋港別情報で決める
        if (
            ship is None
            or ship.assumed_operating
            or ship.status
            in (
                None,
                OperationStatusEnum.cancelled,
                OperationStatusEnum.suspended,
                OperationStatusEnum.no_service,
            )
        ):
            return None
        notice = next(
            (
                n
                for n in self._ship_notices(ship)
                if n.port_id == port_id and n.kind == "skip"
            ),
            None,
        )
        if notice is None:
            return None
        stops = {s.port_id: s for s in self._stops.get(route_id, [])}
        if port_id not in stops:
            return None
        end_offset = max(stops.values(), key=lambda s: s.stop_order).day_offset
        departure_date = cur[1].date() - timedelta(
            days=end_offset - stops[port_id].day_offset
        )
        return notice.sentence if departure_date == d else None

    def _recorded_voyages(
        self, now: datetime, searched: list[tuple[str, int, datetime]]
    ) -> list[tuple[str, int, datetime]]:
        """前回までに記録した、まだ着いていない便の (船名, route_id, 下船日時)。

        同じ船・同じ航路で下船日時が24時間以内なら同じ便とみなす（1往復に2日以上かかるので、
        同じ航路を1日に2回走ることはない）。今回の検索に出てくる便は検索のほうを使い、
        記録した行どうしで時刻が違えば、最後に確認した行の時刻を使う。
        """
        route_ids = [r.id for r in self._load_routes() if r]
        if not route_ids:
            return []
        rows = self.session.execute(
            select(
                DepartureStatus.ship_name,
                DepartureStatus.route_id,
                DepartureStatus.scheduled_arrival_at,
                func.max(DepartureStatus.checked_at).label("checked_at"),
            )
            .where(
                DepartureStatus.route_id.in_(route_ids),
                DepartureStatus.ship_name != "",
                DepartureStatus.scheduled_arrival_at > now,
            )
            .group_by(
                DepartureStatus.ship_name,
                DepartureStatus.route_id,
                DepartureStatus.scheduled_arrival_at,
            )
            .order_by(func.max(DepartureStatus.checked_at).desc())
        ).all()

        same_voyage = timedelta(hours=24)
        accepted = list(searched)
        result: list[tuple[str, int, datetime]] = []
        for r in rows:
            if any(
                ship == r.ship_name
                and route_id == r.route_id
                and abs(arrival - r.scheduled_arrival_at) < same_voyage
                for ship, route_id, arrival in accepted
            ):
                continue
            voyage = (r.ship_name, r.route_id, r.scheduled_arrival_at)
            accepted.append(voyage)
            result.append(voyage)
        return result

    def _future_voyage_status(
        self, ship_name: str, ships: dict[str, ShipInfo], route_id: int, row: SearchRow
    ) -> tuple[OperationStatusEnum | None, str | None]:
        """今の便より後の便の行：抜粋にその便の行があればその状態（全港同じ）、無ければ運航予定。

        港別情報は使わない（FR-004。どの便の話か書いていないことが多い）。
        """
        ship = ships.get(ship_name)
        stops = self._stops.get(route_id, [])
        if ship is None or not ship.voyages or not stops or row.arrival_at is None:
            return None, None
        arrival_date = row.arrival_at.date()
        origin_date = arrival_date - timedelta(
            days=stops[-1].day_offset - stops[0].day_offset
        )
        line = self._voyage_line(ship, route_id, origin_date, arrival_date)
        if line is None:
            return None, None
        if len(ship.voyages) >= 2:
            ship = replace(ship, status=line.status)
        if ship.status is None:
            return None, None
        return ship.status, self._ship_detail_text(ship)

    def _current_voyage_status(
        self,
        ship_name: str,
        ships: dict[str, ShipInfo],
        route_id: int,
        port_id: int,
        d: date,
        departure_at: datetime | None,
    ) -> tuple[OperationStatusEnum, str | None]:
        """今の便の行のステータス：船ステータス（船ブロックに無ければ unknown）に港別情報を重ねる（FR-006）。"""
        ship = ships.get(ship_name)
        if ship is None or ship.status is None:
            self._log.warning(
                "ship_not_found", ship=ship_name, route_id=route_id, port_id=port_id
            )
            return OperationStatusEnum.unknown, None

        original = ship
        ship = self._for_current_voyage(ship)
        if (
            ship.use_recorded
            and ship.tag_over_recorded
            and (departure_at is None or departure_at > datetime.now())
        ):
            ship = original  # まだ出港していない港は、タグのほうが重いのでタグ＋港別情報で決める
        if ship.use_recorded:
            # 港別情報は見ない。前回その港に付けたステータスのまま（無ければその便で一番重いもの）
            arrival_at = self._current_voyage[ship_name][1]
            recorded = self._recorded_voyage(ship_name, route_id, arrival_at)
            if (port_id, d) in recorded.ports:
                return recorded.ports[(port_id, d)]
            return ship.status, recorded.worst_detail
        if ship.assumed_operating:
            return OperationStatusEnum.operating, None
        if ship.status in (
            OperationStatusEnum.cancelled,
            OperationStatusEnum.suspended,
            OperationStatusEnum.no_service,
        ):
            return ship.status, self._ship_detail_text(ship)

        notices = self._ship_notices(ship)
        notice = next((n for n in notices if n.port_id == port_id), None)
        if notice is not None:
            status = (
                OperationStatusEnum.skipped
                if notice.kind == "skip"
                else OperationStatusEnum.delayed
            )
            detail = notice.sentence
            if notice.change_to and notice.change_to not in detail:
                detail += f"（変更先：{notice.change_to}）"
            return status, detail
        if ship.conditional and not ship.schedule_changed and notices:
            # 条件付の理由は言及された港にあるとみなす（遅延・スケジュール変更の船は全港そのまま）
            return OperationStatusEnum.operating, None
        return ship.status, self._ship_detail_text(ship)

    def _ship_notices(self, ship: ShipInfo) -> list[PortNotice]:
        """船ごとの港別情報（1回の実行で1度だけ抜き出す）。"""
        if ship.name not in self._notices:
            text = extract_notice_text(
                ship.excerpt, getattr(self, "_ship_details", {}).get(ship.name)
            )
            notices = extract_port_notices(text, self._resolver)
            if ship.conditional and not notices:
                self._log.warning(
                    "port_notice_unmatched", ship=ship.name, text=text[:200]
                )
            self._notices[ship.name] = notices
        return self._notices[ship.name]

    def _for_current_voyage(self, ship: ShipInfo) -> ShipInfo:
        """船の今の便の状態にした ShipInfo（今の便が分からなければそのまま）。"""
        cur = getattr(self, "_current_voyage", {}).get(ship.name)
        if cur is None:
            return ship
        route_id, arrival_at = cur
        stops = getattr(self, "_stops", {}).get(route_id, [])
        if not stops:
            return ship
        origin_date = arrival_at.date() - timedelta(
            days=stops[-1].day_offset - stops[0].day_offset
        )
        return self._for_voyage(ship, route_id, origin_date, arrival_at)

    def _for_voyage(
        self,
        ship: ShipInfo,
        route_id: int,
        origin_date: date,
        arrival_at: datetime | None,
    ) -> ShipInfo:
        """今の便（始発港の出港日・方向・下船日時）の状態にした ShipInfo。

        タグは全便ぶんなので、別の便の「欠航」が付いていることがある。
        - 便の行が0、またはタグが読めない船 → 船のまま
        - 行が合う → 行が1つだけならタグ（抜粋の文より確か）、2つ以上なら行の状態
        - 行が1つ以上あるのに合わない（公式は変更のある便に行を書く。FR-011）
          - 出港前 → 通常運航。ただし行の無い便の変更かもしれないとき（タグのほうが重い等）は船のまま
          - 出港済み → 前回記録したステータス（公式は過ぎた便の行を消すので、行が無いのは根拠にならない）
        港の行ごとに何度も呼ばれるので、結果は (船名, route_id, 出港日, 下船日時) でキャッシュする（警告も1回）。
        """
        if ship.status is None or not ship.voyages:
            return ship
        if not hasattr(self, "_voyage_cache"):
            self._voyage_cache = {}
        key = (ship.name, route_id, origin_date, arrival_at)
        if key not in self._voyage_cache:
            self._voyage_cache[key] = self._match_voyage(
                ship, route_id, origin_date, arrival_at
            )
        return self._voyage_cache[key]

    def _voyage_line(
        self, ship: ShipInfo, route_id: int, origin_date: date, arrival_date: date
    ) -> VoyageStatus | None:
        """その便（始発港の出港日〜下船日・方向）に合う抜粋の行。無ければ None。

        1. 出港日が同じ行を優先する
        2. 無ければ、途中の港から書いた行だけ、出港日〜下船日の範囲で合わせる（R1・R7）
        """
        direction = self._route_directions().get(route_id)
        same_direction = [v for v in ship.voyages if v.direction == direction]
        exact = next(
            (v for v in same_direction if v.departure_date == origin_date), None
        )
        if exact is not None:
            return exact
        return next(
            (
                v
                for v in same_direction
                if v.from_midway and origin_date <= v.departure_date <= arrival_date
            ),
            None,
        )

    def _match_voyage(
        self,
        ship: ShipInfo,
        route_id: int,
        origin_date: date,
        arrival_at: datetime | None,
    ) -> ShipInfo:
        arrival_date = arrival_at.date() if arrival_at else origin_date
        voyage = self._voyage_line(ship, route_id, origin_date, arrival_date)
        if voyage is not None:
            if len(ship.voyages) < 2:
                return ship
            return replace(
                ship,
                status=voyage.status,
                conditional=voyage.conditional,
                schedule_changed=voyage.schedule_changed,
            )

        def warn(assumed: str) -> None:
            self._log.warning(
                "voyage_not_in_excerpt",
                ship=ship.name,
                route_id=route_id,
                date=str(origin_date),
                assumed=assumed,
            )

        worst_line = max(_SEVERITY.get(v.status, 0) for v in ship.voyages)
        tag_heavier = _SEVERITY.get(ship.status, 0) > worst_line
        conditional_missing = ship.conditional and not any(
            v.conditional for v in ship.voyages
        )
        # 行の無い便の変更（欠航・条件付）がどこかにあり、今の便かもしれない
        tag_unsafe = tag_heavier or conditional_missing
        if tag_unsafe:
            self._log.warning(
                "voyage_tag_heavier_than_lines",
                ship=ship.name,
                route_id=route_id,
                date=str(origin_date),
                tag=ship.status.value,
                heaviest_line=max(
                    (v.status for v in ship.voyages),
                    key=lambda st: _SEVERITY.get(st, 0),
                ).value,
                reason="tag_heavier" if tag_heavier else "conditional_missing",
            )

        if self._voyage_departed(ship.name, route_id, origin_date, arrival_at):
            recorded = self._recorded_voyage(ship.name, route_id, arrival_at)
            if recorded.worst is None:
                warn("ship_status")
                return ship
            warn("recorded")
            return replace(
                ship,
                status=recorded.worst,
                use_recorded=True,
                tag_over_recorded=tag_unsafe,
            )

        if tag_unsafe:
            return ship
        warn("operating")
        return replace(
            ship,
            status=OperationStatusEnum.operating,
            conditional=False,
            schedule_changed=False,
            assumed_operating=True,
        )

    def _voyage_departed(
        self,
        ship_name: str,
        route_id: int,
        origin_date: date,
        arrival_at: datetime | None,
    ) -> bool:
        """その便がもう出港したか（R7）。始発の出港日が今日より前、または一番早い乗船日時が今以前。"""
        if arrival_at is None:
            return False
        if origin_date < getattr(self, "_valid_date", date.today()):
            return True
        times = [
            row.departure_at
            for (rid, _, _), rows in getattr(self, "_searches", {}).items()
            if rid == route_id
            for row in rows or []
            if not row.is_other_company
            and row.ship_name == ship_name
            and row.arrival_at == arrival_at
            and row.departure_at is not None
        ]
        times.extend(self._recorded_voyage(ship_name, route_id, arrival_at).departures)
        return bool(times) and min(times) <= datetime.now()

    def _recorded_voyage(
        self, ship_name: str, route_id: int, arrival_at: datetime
    ) -> RecordedVoyage:
        """前回までに記録したその便の行。同じ船・同じ航路で下船日時の差が24時間未満なら同じ便（1回の実行で1度だけ引く）。"""
        if not hasattr(self, "_recorded_cache"):
            self._recorded_cache = {}
        key = (ship_name, route_id, arrival_at)
        if key not in self._recorded_cache:
            same_voyage = timedelta(hours=24)
            rows = self.session.execute(
                select(
                    DepartureStatus.port_id,
                    DepartureStatus.departure_date,
                    DepartureStatus.status,
                    DepartureStatus.status_detail,
                    DepartureStatus.scheduled_departure_at,
                ).where(
                    DepartureStatus.ship_name == ship_name,
                    DepartureStatus.route_id == route_id,
                    DepartureStatus.scheduled_arrival_at > arrival_at - same_voyage,
                    DepartureStatus.scheduled_arrival_at < arrival_at + same_voyage,
                )
            ).all()
            ports = {
                (r.port_id, r.departure_date): (
                    OperationStatusEnum(r.status),
                    r.status_detail,
                )
                for r in rows
                if r.status is not None
            }
            known = [(st, detail) for st, detail in ports.values() if st in _SEVERITY]
            heaviest = max(known, key=lambda x: _SEVERITY[x[0]]) if known else None
            self._recorded_cache[key] = RecordedVoyage(
                ports=ports,
                departures=tuple(
                    r.scheduled_departure_at
                    for r in rows
                    if r.scheduled_departure_at is not None
                ),
                worst=heaviest[0] if heaviest else None,
                worst_detail=heaviest[1] if heaviest else None,
            )
        return self._recorded_cache[key]

    def _route_directions(self) -> dict[int, str]:
        if not hasattr(self, "_directions"):
            down, up = self._load_routes()
            self._directions = {
                r.id: label for r, label in ((down, "下り"), (up, "上り")) if r
            }
        return self._directions

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_ships(self, html: str) -> dict[str, ShipInfo]:
        """鹿児島航路ページの船ブロック → 船名ごとの ShipInfo。"""
        soup = BeautifulSoup(html, "lxml")
        ships: dict[str, ShipInfo] = {}
        for ferry_name_div in soup.find_all("div", class_="ferry-name"):
            block = ferry_name_div.find_parent("a")
            if block is None:
                continue
            name = ferry_name_div.get_text(strip=True)
            # タグは全部読む（並び順で結果が変わらないように。一番重いものが船のステータス）
            tag_texts: list[str] = []
            tag_spans = block.select("div.tag-list span")
            if not tag_spans:
                self._log.warning("tag_span_not_found", ship=name)
            for tag_span in tag_spans:
                text = tag_span.get_text(strip=True)
                if self._parse_status_text(text) is None:
                    self._log.warning("unknown_status_text", ship=name, text=text[:60])
                    continue
                tag_texts.append(text)
            status, conditional, schedule_changed = self._classify(tag_texts)
            excerpt_div = block.find("div", class_="situation-excerpt")
            excerpt = excerpt_div.get_text(strip=True) if excerpt_div else None
            ships[name] = ShipInfo(
                name,
                status,
                excerpt or None,
                block.get("href"),
                conditional=conditional,
                schedule_changed=schedule_changed,
                voyages=self._parse_voyages(excerpt or ""),
            )
        return ships

    def _classify(
        self, texts: list[str]
    ) -> tuple[OperationStatusEnum | None, bool, bool]:
        """タグ（または便の行の「・」区切り）→ (一番重いステータス, 条件付か, 遅延・スケジュール変更か)。"""
        parsed = [(t, self._parse_status_text(t)) for t in texts]
        known = [(t, st) for t, st in parsed if st is not None]
        status = (
            max((st for _, st in known), key=lambda s: _SEVERITY.get(s, 0))
            if known
            else None
        )
        conditional = any(w in t for t, _ in known for w in _CONDITIONAL_WORDS)
        schedule_changed = any("遅延" in t or "スケジュール変更" in t for t, _ in known)
        return status, conditional, schedule_changed

    def _parse_voyages(self, excerpt: str) -> tuple[VoyageStatus, ...]:
        """抜粋の便ごとの行を読む。年は今日にいちばん近い日付になる年。"""
        today = getattr(self, "_valid_date", None) or date.today()
        voyages: list[VoyageStatus] = []
        for m in _VOYAGE_LINE.finditer(excerpt):
            month, day = int(m.group("month")), int(m.group("day"))
            candidates = []
            for year in (today.year - 1, today.year, today.year + 1):
                try:
                    candidates.append(date(year, month, day))
                except ValueError:
                    continue
            if not candidates:
                continue
            departure_date = min(candidates, key=lambda d: abs((d - today).days))
            # 状態の語だけを見る。補足（「（与論港は欠航の可能性あり）」「※…欠航となる場合が…」）は捨てる
            words = _VOYAGE_STATUS_END.split(m.group("status"), maxsplit=1)[0]
            status, conditional, schedule_changed = self._classify(
                re.split(r"[・、]", words)
            )
            if status is None:
                self._log.warning("unknown_voyage_status", text=m.group(0)[:80])
                continue
            voyages.append(
                VoyageStatus(
                    departure_date,
                    m.group("direction"),
                    status,
                    conditional,
                    schedule_changed,
                    from_midway=self._is_from_midway(
                        m.group("place"), m.group("direction")
                    ),
                )
            )
        return tuple(voyages)

    def _is_from_midway(self, place: str, direction: str) -> bool:
        """日付と方向の間の文字列の、最後の「発」より前の港が、その方向の航路の途中の港か。"""
        port = self._get_resolver().resolve(place.rpartition("発")[0])
        if port is None:
            return False
        route_id = next(
            (
                rid
                for rid, label in self._route_directions().items()
                if label == direction
            ),
            None,
        )
        stops = self._get_stops().get(route_id, [])
        return any(s.port_id == port.id for s in stops[1:-1])

    def _get_resolver(self) -> PortResolver:
        if not hasattr(self, "_resolver"):
            self._resolver = PortResolver.from_session(self.session)
        return self._resolver

    def _get_stops(self) -> dict[int, list[RouteStop]]:
        if not hasattr(self, "_stops"):
            self._stops = self._load_stops([r for r in self._load_routes() if r])
        return self._stops

    def _load_routes(self) -> tuple:
        """(down_route, up_route) を返す。origin_port で判定。"""
        routes = (
            self.session.execute(
                select(Route).where(
                    Route.ferry_company_id == self.company_id,
                    Route.active.is_(True),
                )
            )
            .scalars()
            .all()
        )
        down = next((r for r in routes if r.origin_port == "鹿児島"), None)
        up = next((r for r in routes if r.origin_port == "那覇"), None)
        return down, up

    def _load_stops(self, routes: list[Route]) -> dict[int, list[RouteStop]]:
        if not routes:
            return {}
        rows = (
            self.session.execute(
                select(RouteStop)
                .where(RouteStop.route_id.in_([r.id for r in routes]))
                .order_by(RouteStop.route_id, RouteStop.stop_order)
            )
            .scalars()
            .all()
        )
        result: dict[int, list[RouteStop]] = {}
        for row in rows:
            result.setdefault(row.route_id, []).append(row)
        return result

    def _load_port_codes(self) -> dict[int, str]:
        rows = (
            self.session.execute(
                select(PortCompanyCode).where(
                    PortCompanyCode.ferry_company_id == self.company_id
                )
            )
            .scalars()
            .all()
        )
        return {r.port_id: r.external_code for r in rows}

    def _marix_company_id(self) -> int | None:
        return self.session.execute(
            select(FerryCompany.id).where(FerryCompany.scraper_class == "MarixLine")
        ).scalar()

    def _parse_status_text(self, text: str) -> OperationStatusEnum | None:
        """鹿児島ページの div.tag-list 内の span テキストからステータスを判定。"""
        if "欠航" in text:
            return OperationStatusEnum.cancelled
        if any(w in text for w in _CONDITIONAL_WORDS):
            return OperationStatusEnum.delayed
        if "遅延" in text or "スケジュール変更" in text:
            return OperationStatusEnum.delayed
        if "運休" in text:
            return OperationStatusEnum.suspended
        if "通常" in text:
            return OperationStatusEnum.operating
        # 臨時便は運休・条件付などの語が無いときだけ（先に当てると「臨時便運休」が運航になる）。
        # 「臨時休航」「臨時欠便」のように休・欠を含む言い方も運航にはしない（読めない扱いで警告する）
        if "臨時" in text and not any(w in text for w in ("休", "欠")):
            return OperationStatusEnum.operating
        return None


# 抜粋の便ごとの行。「■10月20日(火)那覇発上り便…条件付き運航・寄港地変更」
# 「10/5(月)鹿児島新港18:00発／下り便…スケジュール変更・条件付運航」。次の行の日付の手前まで
_VOYAGE_LINE = re.compile(
    r"(?P<month>\d{1,2})(?:月|/)(?P<day>\d{1,2})日?\s*[(（][^)）]*[)）]"
    r"(?P<place>[^…■]*?)(?P<direction>上り|下り)便?\s*(?:…|\.{3})+\s*"
    r"(?P<status>.+?)(?=■|\d{1,2}(?:月|/)\d{1,2}日?\s*[(（]|$)",
    re.S,
)
# 便の行の状態の語の終わり（この手前までが「条件付き運航・寄港地変更」）
_VOYAGE_STATUS_END = re.compile(r"[（(※。\s]")


def _parse_search_datetime(text: str) -> datetime | None:
    """「2026年10月4日 05:50」→ datetime。「－」などは None。"""
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{2})", text)
    if not m:
        return None
    try:
        return datetime(*(int(g) for g in m.groups()))
    except ValueError:
        return None


def _iso(v: datetime | None) -> str | None:
    return v.isoformat() if v else None
