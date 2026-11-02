"""
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
       ただし抜粋に便の行がある日付と、前回に船名つきで重い状態（欠航・運休・条件付）を付けた日付は、
       間隔に関係なく毎回検索する（公式の発表をすぐ反映し、行が消えたらすぐ運航予定に戻すため）
     - 検索の間に MARUE_SEARCH_DELAY_SECONDS 待つ
  3. 船別詳細ページ: 各船の a[href] を GET（港別情報と臨時便の抽出に使う）

検索結果（table.s-result tbody tr）:
    <td>鹿児島航路</td><td>フェリーあけぼの</td><td>2026年10月4日 05:50</td><td>2026年10月4日 19:00</td>
    <td>352km</td><td>マルエーフェリー</td>
    - 乗船日時 = その港の出港日時、下船日時 = 到着港への到着日時
    - 他社運航の日は 船名「※下記参照」・会社名「マリックスライン㈱」・日時「－」

raw_html_hash: 鹿児島航路ページの HTML ＋ 今日の始発港2つの検索結果を正規化した文字列 ＋ 航路ごとの「今日の始発港の便が出港済みか」
  （出港時刻をまたぐと、同じ HTML でも航路単位の判定が変わるため）
valid_date: 常に date.today()
"""

import json
import time
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup
from sqlalchemy import func, select

from scraper.config import settings
from scraper.db.models import (
    DepartureStatus,
    OperationStatusEnum,
    Route,
)
from scraper.scrapers.marue_ferry.common import (
    SEARCH_URL,
    KAGOSHIMA_URL,
    SEARCH_ROWS,
    SearchRow,
    ShipInfo,
    RecordedVoyage,
    ExtraParse,
    parse_search_datetime,
    iso_or_none,
)
from scraper.scrapers.marue_ferry.state import MarueState


class FetchMixin(MarueState):
    # ------------------------------------------------------------------
    # fetch
    # ------------------------------------------------------------------

    def fetch(self) -> str:
        self._reset_caches()
        self._valid_date = date.today()
        self._searches: dict[tuple[int, int, date], list[SearchRow] | None] = {}
        self._search_count = 0
        self._recorded_cache: dict[tuple[str, int, datetime], RecordedVoyage] = {}

        routes = [r for r in self._routes if r]
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

        # 船別詳細ページの臨時便（取れなかった船は None＝行も作らず、消しもしない）
        self._extra_voyages: dict[str, ExtraParse | None] = {
            name: self._parse_extra_voyages(detail, name)
            for name, detail in self._ship_details.items()
        }

        # 方向ごとの便有無が変わったら raw_html_hash も変わるように、今日の始発港の検索結果をつなげる
        return (
            resp.text
            + "\n<!-- searches: "
            + self._normalized_origin_searches(routes)
            + " -->"
            # 同じ検索結果のまま出港時刻をまたいだら、航路単位（出港前後で判定が変わる）も更新する
            + "\n<!-- departed: "
            + self._origin_departed(routes, now)
            + " -->"
        )

    def _voyage_search_keys(self, routes: list[Route]) -> set[tuple[int, int, date]]:
        """抜粋の便の行から決まる、2日先以降の検索キー（間隔に関係なく検索する。R5）。

        途中の港から書いた行（from_midway）は始発の出港日が1日前のこともあるので、行の日付と前日の両方を
        始発の出港日とみなす。始発港の行は行の日付だけ（前日の存在しない便は検索しない）。
        """
        directions = self._directions
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
                starts = [voyage.departure_date]
                if voyage.from_midway:
                    starts.append(voyage.departure_date - timedelta(days=1))
                for start in starts:
                    for stop in stops[:-1]:
                        d = start + timedelta(
                            days=stop.day_offset - stops[0].day_offset
                        )
                        if first <= d <= last:
                            keys.add((route.id, stop.port_id, d))
        return keys

    def _recorded_search_keys(self, routes: list[Route]) -> set[tuple[int, int, date]]:
        """前回に状態を付けた 2日先以降のキーも、間隔に関係なく検索する（便の行が消えたとき。R5）。

        取り消されたときに古いままだと困る重い状態だけ。ship_name が空の行（他社運航・0件）・skipped・NULL・
        通常運航（operating）の行は含めない。含めると行が残るあいだ毎回検索になり、間隔がほぼ効かなくなる。
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
                SEARCH_ROWS,
                DepartureStatus.ship_name != "",
                DepartureStatus.status.in_(
                    [
                        s.value
                        for s in (
                            OperationStatusEnum.cancelled,
                            OperationStatusEnum.suspended,
                            OperationStatusEnum.delayed,
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
                SEARCH_ROWS,
            )
        ).scalar()
        if last_checked is None:
            return True
        return last_checked < now - timedelta(
            hours=settings.marue_far_search_interval_hours
        )

    def _origin_departed(self, routes: list[Route], now: datetime) -> str:
        """航路ごとの、今日の始発港の便が出港済みか（raw_html_hash に入れる）。"""
        result = {}
        for route in routes:
            stops = self._stops.get(route.id, [])
            rows = (
                self._searches.get((route.id, stops[0].port_id, self._valid_date))
                if stops
                else None
            )
            first = next((r for r in rows or [] if not r.is_other_company), None)
            result[str(route.id)] = bool(
                first and first.departure_at and first.departure_at <= now
            )
        return json.dumps(result, sort_keys=True)

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
                        iso_or_none(r.departure_at),
                        iso_or_none(r.arrival_at),
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
            departure_at = parse_search_datetime(dep_text)
            arrival_at = parse_search_datetime(arr_text)
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
