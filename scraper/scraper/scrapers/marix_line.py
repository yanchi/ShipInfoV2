"""
MarixLine (マリックスライン) scraper.

Target: https://marixline.com/service/
Actual HTML structure (confirmed 2026-03-07):
    <div class="status_single_cover normal">
      <a class="status_single normal" href="...">
        <div class="info1">
          <p class="exp">通常運航</p>
        </div>
        <div class="info2">
          2026年3月7日 鹿児島新港発 2026年3月8日 那覇港 向け   ← 下り
        </div>
      </a>
    </div>
    <div class="status_single_cover conditional alert">
      <a class="status_single conditional alert" href="...">
        <div class="info1">
          <p class="exp">条件付運航</p>
        </div>
        <div class="info2">
          2026年3月7日 那覇港発 2026年3月8日 鹿児島新港 向け   ← 上り
        </div>
      </a>
    </div>

CSS class → status mapping (div.status_single_cover・詳細ページの div.single のクラスで判定):
    normal              → operating
    conditional alert   → delayed（条件付運航）
    route alert         → delayed（航行経路変更。運航はする）
    cancel alert        → cancelled（欠航）
    alert だけ          → cancelled（2026-03 時点の一覧の欠航）
    no_status           → cancelled（詳細ページの港のみ。「―」寄港しません＝抜港。
                          2025-10〜2026-10 の1年分では、航行経路変更の便にだけ出ていた）
    それ以外            → unknown（読み飛ばすと前回のステータスが残るので書く）
    ※「運航遅延」は見出しの【】に出るだけで、港のクラスは conditional・route だった（同じ1年分）

Direction (div.info2 の出発港で判定):
    "鹿児島" + "発" → 下り（鹿児島 → 那覇）
    "那覇"   + "発" → 上り（那覇 → 鹿児島）

Date: div.info2 の最初の "YYYY年M月D日" を valid_date として使用

港別（parse_departures、research R1）:
    一覧の各便 a.status_single[href] が便別詳細ページ（例：/service/upstream20260930/）。
    詳細ページの構造（確認済み 2026-10-01）:
        <div class="inner_wrap">
          <h1 class="heading1">2026年9月30日（水） 那覇港発 … 上り便【条件付運航】</h1>
          <h4>クイーンコーラルプラス</h4>                      ← 船名（最初の h4）
          <h4>海上荒天(台風)の影響による船舶動静</h4>          ← 理由（あれば）
          <div class="service">
            <div class="single conditional alert">             ← 港ごと。class は一覧と同じ語彙
              <span class="port_name">与論港</span>
              <div class="exp sub">下記の詳細条件を確認してください</div>
              <div class="entry sub">…<span class="date">09月30日</span><span class="time">11:50</span></div>
              <div class="departure sub">…<span class="date">09月30日</span><span class="time">12:10</span></div>
            </div>
            …（始発港は出港のみ、終点は入港のみ）
          </div>
        </div>
    - 出入港日時に年が無いので、一覧の始発日の年で補う（始発日より前の月日なら翌年）
    - 寄港順（route_stops）のうち終点以外の港について行を作る。到着予定は終点の入港日時
    - 詳細ページが取れない便は、便全体のステータスを全出発港に当てはめ、出港日は始発日 + day_offset、
      時刻は None にする（予備ルート）。ただし詳細ページから取れた行（船名あり）がすでにあれば、そちらを残す
"""

import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag
from sqlalchemy import select

from scraper.db.models import DepartureStatus, OperationStatusEnum, Route, RouteStop
from scraper.scrapers.base import BaseScraper
from scraper.utils.ports import PortResolver

SOURCE_URL = "https://marixline.com/service/"

# 一覧（div.status_single_cover）と詳細ページの港（div.single）で共通のステータスのクラス
# （実例: 2026-06-24 航行経路変更、2026-06-26 欠航）
_STATUS_BY_CLASS = {
    "normal": OperationStatusEnum.operating,
    "conditional": OperationStatusEnum.delayed,  # 条件付運航
    "route": OperationStatusEnum.delayed,  # 航行経路変更（運航はする。寄らない港は no_status）
    "cancel": OperationStatusEnum.cancelled,
}
# ステータスを表さないクラス（alert は条件付・経路変更・欠航のどれにも付く）
_LAYOUT_CLASSES = {
    "status_single_cover",
    "status_single",
    "single",
    "firstport",
    "alert",
}
# 詳細ページで、その港に寄らない（表示は「―」「寄港しません」）
_SKIPPED_PORT_CLASS = "no_status"


class MarixLine(BaseScraper):
    def fetch(self) -> str:
        resp = self.http.get(SOURCE_URL, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        self._list_html = resp.text

        # 便別詳細ページ（失敗しても続ける。港別は予備ルートになる）
        self._detail_pages: dict[str, str | None] = {}
        soup = BeautifulSoup(resp.text, "lxml")
        for a in soup.select("div.status_single_cover a.status_single[href]"):
            url = urljoin(SOURCE_URL, a["href"])
            if url in self._detail_pages:
                continue
            try:
                detail = self.http.get(url, timeout=30)
                detail.raise_for_status()
                detail.encoding = detail.apparent_encoding
                self._detail_pages[url] = detail.text
            except Exception as exc:
                self._log.warning("detail_fetch_failed", url=url, error=str(exc))
                self._detail_pages[url] = None

        # 戻り値は今までどおり一覧の HTML（raw_html_hash の意味を変えない）
        return resp.text

    def parse(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        down_route, up_route = self._load_routes()
        records: list[dict] = []
        seen: set[tuple[int, date]] = set()

        for block in soup.find_all("div"):
            cls = block.get("class", [])
            if "status_single_cover" not in cls:
                continue

            info2 = block.find("div", class_="info2")
            if not info2:
                continue
            info2_text = info2.get_text(separator=" ", strip=True)

            valid_date = self._parse_date(info2_text)
            if valid_date is None:
                continue

            direction = self._parse_direction(info2_text)
            if direction == "down":
                route = down_route
            elif direction == "up":
                route = up_route
            else:
                self._log.warning("direction_unknown", info2=info2_text[:60])
                continue

            if route is None:
                self._log.warning("route_not_found", direction=direction)
                continue

            key = (route.id, valid_date)
            if key in seen:
                continue
            seen.add(key)

            status = self._parse_status_from_classes(cls)
            if status is None:
                # 読み飛ばすと前回のステータス（通常運航など）が残るので unknown で書く
                self._log.warning("unknown_status_class", classes=cls)
                status = OperationStatusEnum.unknown

            exp = block.find("p", class_="exp")
            exp_text = exp.get_text(strip=True) if exp else None
            detail = exp_text if status != OperationStatusEnum.operating else None

            records.append(
                {
                    "route_id": route.id,
                    "status": status,
                    "status_detail": detail,
                    "valid_date": valid_date,
                    "scraped_at": datetime.now(),
                    "source_url": SOURCE_URL,
                }
            )

        # 今日の便が存在しないルートに no_service を記録
        # （日付は info2 の最初の日付＝出発日なので、到着日としてのみ今日がある便は「便なし」）
        today = date.today()
        now = datetime.now()
        for route in [r for r in [down_route, up_route] if r]:
            if (route.id, today) not in seen:
                records.append(
                    {
                        "route_id": route.id,
                        "status": OperationStatusEnum.no_service,
                        "status_detail": None,
                        "valid_date": today,
                        "scraped_at": now,
                        "source_url": SOURCE_URL,
                    }
                )

        self._log.info("parsed", records=len(records))
        return records

    # ------------------------------------------------------------------
    # 港別（departure_statuses）
    # ------------------------------------------------------------------

    def parse_departures(self) -> list[dict]:
        list_html = getattr(self, "_list_html", None)
        if not list_html:
            return []
        detail_pages = getattr(self, "_detail_pages", {})
        resolver = PortResolver.from_session(self.session)
        down_route, up_route = self._load_routes()
        stops = self._load_stops([r for r in (down_route, up_route) if r])

        soup = BeautifulSoup(list_html, "lxml")
        records: list[dict] = []
        for block in soup.select("div.status_single_cover"):
            # 便のクラスを読めなくても、詳細ページの港ごとのクラスで判定する（parse で warning 済み）
            status = (
                self._parse_status_from_classes(block.get("class", []))
                or OperationStatusEnum.unknown
            )
            info2 = block.find("div", class_="info2")
            link = block.select_one("a.status_single[href]")
            if info2 is None or link is None:
                continue
            info2_text = info2.get_text(separator=" ", strip=True)
            start_date = self._parse_date(info2_text)
            direction = self._parse_direction(info2_text)
            route = {"down": down_route, "up": up_route}.get(direction or "")
            if start_date is None or route is None or not stops.get(route.id):
                self._log.warning("departure_block_skipped", info2=info2_text[:60])
                continue

            url = urljoin(SOURCE_URL, link["href"])
            detail_html = detail_pages.get(url)
            detail_records = (
                self._departures_from_detail(
                    detail_html,
                    route,
                    stops[route.id],
                    start_date,
                    status,
                    url,
                    resolver,
                )
                if detail_html
                else None
            )
            if detail_records:
                records.extend(detail_records)
                continue

            self._log.warning("departure_fallback", url=url, route_id=route.id)
            exp = block.find("p", class_="exp")
            detail = (
                exp.get_text(strip=True)
                if exp and status != OperationStatusEnum.operating
                else None
            )
            records.extend(
                self._fallback_departures(
                    route, stops[route.id], start_date, status, detail, url
                )
            )

        self._log.info("parsed_departures", records=len(records))
        return records

    def _departures_from_detail(
        self,
        html: str,
        route: Route,
        stops: list[RouteStop],
        start_date: date,
        voyage_status: OperationStatusEnum,
        url: str,
        resolver: PortResolver,
    ) -> list[dict] | None:
        """便別詳細ページから、終点以外の寄港地の行を作る。解析できなければ None。"""
        soup = BeautifulSoup(html, "lxml")
        singles = soup.select("div.service > div.single")
        if not singles:
            self._log.warning("detail_structure_unknown", url=url)
            return None

        stop_port_ids = {s.port_id for s in stops}
        terminal_port_id = stops[-1].port_id
        by_port: dict[int, dict] = {}
        for single in singles:
            name_el = single.select_one("span.port_name")
            name = name_el.get_text(strip=True) if name_el else ""
            port = resolver.resolve(name)
            if port is None or port.id not in stop_port_ids:
                self._log.warning("detail_port_not_in_stops", url=url, port=name)
                continue
            classes = single.get("class", [])
            status = (
                OperationStatusEnum.cancelled
                if _SKIPPED_PORT_CLASS in classes
                else self._parse_status_from_classes(classes)
            )
            if status is None:
                self._log.warning(
                    "detail_status_unknown",
                    url=url,
                    port=name,
                    classes=single.get("class"),
                )
                status = OperationStatusEnum.unknown
            exp = single.select_one("div.exp")
            by_port[port.id] = {
                "status": status,
                "exp": exp.get_text(strip=True) if exp else None,
                "entry_at": self._parse_detail_time(
                    single.select_one("div.entry"), start_date
                ),
                "departure_at": self._parse_detail_time(
                    single.select_one("div.departure"), start_date
                ),
            }

        ship_name, reasons = self._parse_detail_heading(
            soup, with_notes=voyage_status != OperationStatusEnum.operating
        )
        arrival_at = by_port.get(terminal_port_id, {}).get("entry_at")
        records: list[dict] = []
        for stop in stops[:-1]:
            info = by_port.get(stop.port_id)
            if info is None:
                self._log.warning("detail_stop_missing", url=url, port_id=stop.port_id)
                continue
            departure_at = info["departure_at"]
            departure_date = (
                departure_at.date()
                if departure_at
                else start_date + timedelta(days=stop.day_offset)
            )
            detail = None
            if info["status"] != OperationStatusEnum.operating:
                detail = " ".join(t for t in [*reasons, info["exp"]] if t) or None
            records.append(
                {
                    "route_id": route.id,
                    "port_id": stop.port_id,
                    "departure_date": departure_date,
                    "ship_name": ship_name,
                    "status": info["status"],
                    "status_detail": detail,
                    "scheduled_departure_at": departure_at,
                    "scheduled_arrival_at": arrival_at,
                    "operated_by_company_id": None,
                    "source_url": url,
                    "freeze_after_departure": False,
                    # 日付で消すと、出港日がずれて同じ日付になった別の便の行まで消えるので使わない（#28）
                    "replace_scope": None,
                    # 同じ便の、今回書かなかった行（予備ルートの行、遅延で前の日付になった行）を消すため
                    # （詳細ページの URL は便ごとに一つ：/service/downstream20260930/。予備ルートの行も同じ URL）
                    "replace_source": (route.id, stop.port_id, url),
                }
            )
        return records or None

    def _fallback_departures(
        self,
        route: Route,
        stops: list[RouteStop],
        start_date: date,
        status: OperationStatusEnum,
        detail: str | None,
        url: str,
    ) -> list[dict]:
        """詳細ページが取れない便：便全体のステータスを全出発港に当てはめる（FR-004）。"""
        records: list[dict] = []
        for stop in stops[:-1]:
            departure_date = start_date + timedelta(days=stop.day_offset)
            # 同じ便の詳細ページの行があるか。出港日がずれていることがあるので日付では探さない
            exists = self.session.execute(
                select(DepartureStatus.id)
                .where(
                    DepartureStatus.route_id == route.id,
                    DepartureStatus.port_id == stop.port_id,
                    DepartureStatus.source_url == url,
                    # 予備ルート自身が書いた行（船名なし）は更新したいので、詳細ページの行だけ見る
                    DepartureStatus.ship_name != "",
                )
                .limit(1)
            ).first()
            if exists:
                continue  # 最後に詳細ページから取れた内容を残す（FR-013）
            records.append(
                {
                    "route_id": route.id,
                    "port_id": stop.port_id,
                    "departure_date": departure_date,
                    "ship_name": "",
                    "status": status,
                    "status_detail": detail,
                    "scheduled_departure_at": None,
                    "scheduled_arrival_at": None,
                    "operated_by_company_id": None,
                    "source_url": url,
                    "freeze_after_departure": False,
                    "replace_scope": None,
                }
            )
        return records

    def _parse_detail_heading(
        self, soup: BeautifulSoup, with_notes: bool
    ) -> tuple[str, list[str]]:
        """(船名, 理由の見出し) を返す。船名は h1.heading1 の後の最初の h4。

        理由は残りの h4（「海上荒天(台風)の影響による船舶動静」）と、with_notes なら
        h2（「航行経路を「鹿児島 → 名瀬」に変更し運航」）。通常の便の h2 は
        「通常通り運航します。」なので、便全体が通常運航のときは入れない。
        """
        h1 = soup.select_one("h1.heading1")
        container = h1.parent if h1 else soup
        names = ["h4", "h2"] if with_notes else ["h4"]
        headings = [
            (h.name, h.get_text(strip=True))
            for h in container.find_all(names, recursive=False)
        ]
        headings = [(name, t) for name, t in headings if t]
        first_h4 = next(
            (i for i, (name, _) in enumerate(headings) if name == "h4"), None
        )
        if first_h4 is None:
            return "", []
        ship_name = headings.pop(first_h4)[1]
        return ship_name, [t for _, t in headings]

    def _parse_detail_time(self, el: Tag | None, start_date: date) -> datetime | None:
        """「09月30日 07:00」を始発日の年で補って datetime にする（始発日より前の月日なら翌年）。"""
        if el is None:
            return None
        text = el.get_text(" ", strip=True)
        m = re.search(r"(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{2})", text)
        if not m:
            self._log.warning("detail_time_parse_failed", text=text[:40])
            return None
        month, day, hour, minute = (int(g) for g in m.groups())
        year = start_date.year
        if (month, day) < (start_date.month, start_date.day):
            year += 1
        try:
            return datetime(year, month, day, hour, minute)
        except ValueError:
            self._log.warning("detail_time_invalid", text=text[:40])
            return None

    def _load_stops(self, routes: list[Route]) -> dict[int, list[RouteStop]]:
        """route_id → 寄港順（stop_order 昇順）。"""
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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

    def _parse_status_from_classes(
        self, classes: list[str]
    ) -> OperationStatusEnum | None:
        """ステータスのクラスがちょうど1つあればそのステータス。無い・複数・知らないクラスは None。"""
        matched = {s for c, s in _STATUS_BY_CLASS.items() if c in classes}
        if len(matched) == 1:
            return matched.pop()
        if not matched and "alert" in classes and set(classes) <= _LAYOUT_CLASSES:
            # 2026-03 時点の一覧は、欠航が alert だけだった
            return OperationStatusEnum.cancelled
        return None

    def _parse_direction(self, info2_text: str) -> str | None:
        """'2026年3月7日 鹿児島新港発...' から出発港を判定。"""
        if re.search(r"鹿児島\S*発", info2_text):
            return "down"
        if re.search(r"那覇\S*発", info2_text):
            return "up"
        return None

    def _parse_date(self, info2_text: str) -> date | None:
        """'2026年3月7日 鹿児島新港発...' から最初の日付を取得。"""
        m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", info2_text)
        if not m:
            self._log.warning("date_parse_failed", text=info2_text[:60])
            return None
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            self._log.warning("date_invalid", text=info2_text[:60])
            return None
