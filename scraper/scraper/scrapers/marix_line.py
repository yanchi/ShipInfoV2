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
    temporary           → 便の種類（臨時便）。港の行だけ extra。ほかの状態のクラスが付けばその状態
    no_status           → skipped（詳細ページの港のみ。「―」寄港しません＝抜港。便が欠航・運休ならそちら。
                          2025-10〜2026-10 の1年分では、航行経路変更の便にだけ出ていた）
    ※ skipped は港の行（departure_statuses）だけ。航路単位（operation_statuses）には書かない
    それ以外            → unknown（読み飛ばすと前回のステータスが残るので書く）
    ※「運航遅延」は見出しの【】に出るだけで、港のクラスは conditional・route だった（同じ1年分）

Direction（最初に決まったものを使う。13-marix-extra-voyages R2）:
    1. div.info2 の出発港: "鹿児島" + "発" → 下り（鹿児島 → 那覇）、"那覇" + "発" → 上り（那覇 → 鹿児島）
    2. 一覧の欄: div.down_stream_services の中 → 下り、div.up_stream_services の中 → 上り
    3. 行き先: "那覇… 向け" → 下り、"鹿児島… 向け" → 上り
    名瀬発の臨時便（"名瀬港発 鹿児島新港 向け"）は 1 では決まらないので 2・3 で決める

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

臨時便（13-marix-extra-voyages）。確認した例: 2026-09-06 service6727（鹿児島発・航行経路変更）、
2026-09-07 service6731（那覇発・欠航した定期便の代わり）、2026-09-27 service6819（名瀬発）:
    便の種類（R1）: 一覧の便のクラスに temporary、または詳細ページの見出しに【臨時便…】・寄る港の全部のクラスに
        temporary があれば臨時便。temporary は状態ではなく便の種類（temporary cancel alert は cancelled）。詳細ページが取れなかった便は「分からない」（unknown）。
        fetch() を通っていない呼び方（既存のテスト）は定期便
    港の行（R3）: 臨時便が寄る港（temporary）だけ extra の行にする。寄らない港（no_status）は行も時刻も
        作らない（寄らない港には定期便の時刻や別の日付が残っている）
    同じキーの優先（R4）: 航路・港・出港日・船名が同じ定期便と臨時便は、定期便が欠航・運休・抜港・不明なら
        臨時便の行。定期便が走るなら定期便の行に「（臨時便 HH:MM発あり）」を足して警告する
    前の回の行（R5）: 臨時便の詳細ページが取れない回と、臨時便が出港済み（始発港の出港で便ごと）のときは、
        定期便の欠航で上書きしない。出港前に一覧から消えたら定期便の欠航に戻す
    予備ルート（R6）: 臨時便の詳細ページが取れなければ予備ルートは使わない（extra_voyage_detail_missing）。
        分からない便は今までどおり予備ルートの行を作る
    後始末（R7）: 臨時便の行は replace_source を (航路, None, URL) にして、Base のルール6で書かなくなった行
        （寄らなくなった港・日付がずれた古い行・分からなかった回の予備ルートの行）を消す。同じキーの便に負けて
        書かなかった行と、取りやめた臨時便は、出どころだけ登録する行（source_only）でルール6に渡す
    航路単位（R8）: 臨時便は書かない（operation_statuses の ENUM に extra は無い）。分からない便は、一覧のクラスが
        読めれば控えの行（同じ日に定期便が無いときだけ書く）、読めなければ書かない（voyage_kind_unknown）
"""

import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag
from sqlalchemy import func, select

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
# 臨時便の見分け方（research R1）。temporary は状態ではなく便の種類なので _STATUS_BY_CLASS には入れない
# （入れると `temporary cancel alert` が2つの状態に一致して unknown になる。PR #90 レビュー）。見出しは「【臨時便】」「【臨時便運航】」「【臨時便・航行経路変更】」
_EXTRA_CLASS = "temporary"
_EXTRA_HEADING = "【臨時便"
# 同じキーの定期便がこのステータスなら臨時便の行を優先する（research R4）
_REPLACEABLE_BY_EXTRA = (
    OperationStatusEnum.cancelled,
    OperationStatusEnum.suspended,
    OperationStatusEnum.skipped,
    OperationStatusEnum.unknown,
)
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

        # 便別詳細ページ（失敗しても続ける。港別は予備ルートになる）。パースは URL ごとに1回だけ
        self._detail_pages: dict[str, BeautifulSoup | None] = {}
        # 詳細ページで決めた便の種類（一覧のクラスの temporary は _voyage_kind で見る）
        self._voyage_kinds: dict[str, str] = {}
        soup = BeautifulSoup(resp.text, "lxml")
        for a in soup.select("div.status_single_cover a.status_single[href]"):
            url = urljoin(SOURCE_URL, a["href"])
            if url in self._detail_pages:
                continue
            try:
                detail = self.http.get(url, timeout=30)
                detail.raise_for_status()
                detail.encoding = detail.apparent_encoding
                detail_soup = BeautifulSoup(detail.text, "lxml")
            except Exception as exc:
                self._log.warning("detail_fetch_failed", url=url, error=str(exc))
                self._detail_pages[url] = None
                self._voyage_kinds[url] = "unknown"
                continue
            self._detail_pages[url] = detail_soup
            self._voyage_kinds[url] = self._detail_kind(detail_soup)

        # 戻り値は今までどおり一覧の HTML（raw_html_hash の意味を変えない）
        return resp.text

    def parse(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        down_route, up_route = self._load_routes()
        records: list[dict] = []
        seen: set[tuple[int, date]] = set()
        # 種類が分からない便（詳細ページが取れない）。定期便で埋まらなかったときだけ使う（research R8）
        fallback_records: list[dict] = []
        unknown_keys: set[tuple[int, date]] = set()

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

            direction = self._parse_direction(info2_text, block)
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

            link = block.select_one("a.status_single[href]")
            url = urljoin(SOURCE_URL, link["href"]) if link is not None else None
            kind = self._voyage_kind(block, url)
            if kind == "extra":
                # 臨時便は航路単位に書かない。seen にも入れない（同じ日の定期便を捨てないため）
                continue

            key = (route.id, valid_date)
            if kind == "regular" and key in seen:
                continue

            status = self._parse_status_from_classes(cls)
            if kind == "unknown" and status is None:
                # 一覧のクラスが読めず詳細ページも取れない。「不明」を書くと、一覧の HTML が
                # 変わるまで直らない（raw_html_hash）ので書かない。「便なし」にもしない
                self._log.warning("voyage_kind_unknown", url=url)
                unknown_keys.add(key)
                continue
            if status is None:
                # 読み飛ばすと前回のステータス（通常運航など）が残るので unknown で書く
                self._log.warning("unknown_status_class", classes=cls)
                status = OperationStatusEnum.unknown

            exp = block.find("p", class_="exp")
            exp_text = exp.get_text(strip=True) if exp else None
            detail = exp_text if status != OperationStatusEnum.operating else None

            record = {
                "route_id": route.id,
                "status": status,
                "status_detail": detail,
                "valid_date": valid_date,
                "scraped_at": datetime.now(),
                "source_url": SOURCE_URL,
            }
            if kind == "unknown":
                fallback_records.append(record)
                continue
            seen.add(key)
            records.append(record)

        # 控えの行：同じ航路・日付に定期便が無いときだけ、一覧の順で最初のものを書く
        for record in fallback_records:
            key = (record["route_id"], record["valid_date"])
            if key not in seen:
                seen.add(key)
                records.append(record)
        seen |= unknown_keys

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
        # 前の回に臨時便が書いた行（research R5）。範囲は一覧の便の始発日のいちばん前以降
        list_urls: set[str] = set()
        start_dates: list[date] = []
        for cover in soup.select("div.status_single_cover"):
            link = cover.select_one("a.status_single[href]")
            info2 = cover.find("div", class_="info2")
            if link is not None:
                list_urls.add(urljoin(SOURCE_URL, link["href"]))
            if info2 is not None:
                start = self._parse_date(info2.get_text(separator=" ", strip=True))
                if start is not None:
                    start_dates.append(start)
        kept = self._extra_rows_kept(
            [r.id for r in (down_route, up_route) if r],
            min(start_dates, default=date.today()),
        )
        # この回に詳細ページを読めた臨時便の URL（research R5）
        read_extra_urls: set[str] = set()
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
            direction = self._parse_direction(info2_text, block)
            route = {"down": down_route, "up": up_route}.get(direction or "")
            if start_date is None or route is None or not stops.get(route.id):
                self._log.warning("departure_block_skipped", info2=info2_text[:60])
                continue

            url = urljoin(SOURCE_URL, link["href"])
            detail_soup = detail_pages.get(url)
            kind = self._voyage_kind(block, url)
            if kind == "extra":
                # 臨時便は一覧のクラスに関係なく便全体を extra として読む（research R3）
                status = OperationStatusEnum.extra
            detail_records = (
                self._departures_from_detail(
                    detail_soup,
                    route,
                    stops[route.id],
                    start_date,
                    status,
                    url,
                    resolver,
                )
                if detail_soup is not None
                else None
            )
            if detail_records:
                records.extend(detail_records)
                if kind == "extra":
                    read_extra_urls.add(url)
                continue
            if kind == "extra":
                # 寄る港は詳細ページにしか無いので、予備ルートは使わない（research R6）
                self._log.warning(
                    "extra_voyage_detail_missing", url=url, route_id=route.id
                )
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

        records = self._resolve_extra_conflicts(
            records, kept, list_urls, read_extra_urls
        )
        self._log.info("parsed_departures", records=len(records))
        return records

    def _extra_rows_kept(self, route_ids: list[int], since: date) -> dict[tuple, str]:
        """前の回に臨時便が書いた行（状態 extra）：キー → source_url。"""
        if not route_ids:
            return {}
        rows = self.session.execute(
            select(
                DepartureStatus.route_id,
                DepartureStatus.port_id,
                DepartureStatus.departure_date,
                DepartureStatus.ship_name,
                DepartureStatus.source_url,
            ).where(
                DepartureStatus.route_id.in_(route_ids),
                DepartureStatus.status == OperationStatusEnum.extra.value,
                DepartureStatus.departure_date >= since,
            )
        ).all()
        return {(r[0], r[1], r[2], r[3] or ""): r[4] for r in rows}

    def _extra_first_departures(
        self, route_ids: list[int], urls: set[str]
    ) -> dict[str, datetime | None]:
        """臨時便の URL ごとの、いちばん早い出港予定（始発港の出港）。

        出港日の範囲で絞らない。日をまたぐ便の始発港の行は、途中の港の行より前の出港日になる。
        """
        if not route_ids or not urls:
            return {}
        rows = self.session.execute(
            select(
                DepartureStatus.source_url,
                func.min(DepartureStatus.scheduled_departure_at),
            )
            .where(
                DepartureStatus.route_id.in_(route_ids),
                DepartureStatus.status == OperationStatusEnum.extra.value,
                DepartureStatus.source_url.in_(urls),
            )
            .group_by(DepartureStatus.source_url)
        ).all()
        return {url: first for url, first in rows}

    @staticmethod
    def _departure_key(rec: dict) -> tuple:
        return (
            rec["route_id"],
            rec["port_id"],
            rec["departure_date"],
            rec.get("ship_name") or "",
        )

    def _resolve_extra_conflicts(
        self,
        records: list[dict],
        kept: dict[tuple, str],
        list_urls: set[str],
        read_extra_urls: set[str],
    ) -> list[dict]:
        """同じキー（航路・港・出港日・船名）の臨時便と定期便を1本に絞る（research R4）。

        定期便が欠航・運休・抜港・不明なら臨時便の行、それ以外は定期便の行（詳細に
        「（臨時便 HH:MM発あり）」を足す）。一覧の並び順に関係なく同じ結果になる。
        臨時便同士・定期便同士の重複は触らない（Base が先の行を使う）。返す行は元の順を保つ。

        落とした行の replace_source と、取りやめた臨時便は、書かずに出どころだけ登録する行
        （source_only）を最後に足す。Base のルール6が、書かなくなった古い行を消す（research R7）。
        """
        extras: dict[tuple, dict] = {}
        regulars: dict[tuple, dict] = {}
        by_key: dict[tuple, list[dict]] = {}
        for rec in records:
            key = self._departure_key(rec)
            target = extras if rec.get("extra_voyage") else regulars
            target.setdefault(key, rec)
            by_key.setdefault(key, []).append(rec)

        drop: set[int] = set()  # 落とす行の id()
        for key, extra in extras.items():
            regular = regulars.get(key)
            if regular is None:
                continue
            if regular["status"] in _REPLACEABLE_BY_EXTRA:
                drop.update(id(r) for r in by_key[key] if not r.get("extra_voyage"))
                continue
            # 定期便が走る。臨時便の行を落として、定期便の詳細で気づけるようにする
            at = extra.get("scheduled_departure_at")
            note = f"（臨時便 {at:%H:%M}発あり）" if at else "（臨時便あり）"
            regular["status_detail"] = f"{regular.get('status_detail') or ''}{note}"
            drop.update(id(r) for r in by_key[key] if r.get("extra_voyage"))
            self._log.warning(
                "extra_voyage_conflict",
                key=[str(k) for k in key],
                regular_url=regular["source_url"],
                extra_url=extra["source_url"],
            )

        # 一覧から消えた未出港の臨時便（取りやめ）の URL → 航路。同じキーの定期便が無くても
        # 行が残らないよう、ルール6で便の行を全部消す（PR #90 レビュー）
        vanished: dict[str, int] = {}
        # この回の臨時便の行が無いキー：前の回の臨時便の行を、定期便の欠航で上書きしない（research R5）
        if kept:
            firsts = self._extra_first_departures(
                sorted({k[0] for k in kept}), set(kept.values())
            )
            now = datetime.now()
            # 出港予定が全部 NULL の臨時便は、いちばん早い出港日が今日以前なら出港済みかもしれないとみる
            first_dates: dict[str, date] = {}
            for (_, _, day, _), url in kept.items():
                first_dates[url] = min(day, first_dates.get(url, day))

            def departed(url: str) -> bool:
                first = firsts.get(url)
                if first is not None:
                    return first <= now
                return first_dates[url] <= now.date()

            vanished = {
                url: route_id
                for (route_id, _, _, _), url in kept.items()
                if url not in list_urls and not departed(url)
            }
            for rec in records:
                key = self._departure_key(rec)
                if (
                    rec.get("extra_voyage")
                    or key in extras
                    or key not in kept
                    or rec["status"] not in _REPLACEABLE_BY_EXTRA
                ):
                    continue
                url = kept[key]
                # ① 臨時便は一覧にあるのに詳細ページを読めていない ② 臨時便は出港済み（便ごと）
                if (url in list_urls and url not in read_extra_urls) or departed(url):
                    drop.add(id(rec))

        sources = {
            tuple(r["replace_source"])
            for r in records
            if id(r) in drop and r.get("replace_source")
        }
        sources |= {(route_id, None, url) for url, route_id in vanished.items()}
        return [r for r in records if id(r) not in drop] + [
            {"replace_source": source, "source_only": True}
            for source in sorted(sources, key=str)
        ]

    def _departures_from_detail(
        self,
        soup: BeautifulSoup,
        route: Route,
        stops: list[RouteStop],
        start_date: date,
        voyage_status: OperationStatusEnum,
        url: str,
        resolver: PortResolver,
    ) -> list[dict] | None:
        """便別詳細ページから、終点以外の寄港地の行を作る。解析できなければ None。"""
        singles = soup.select("div.service > div.single")
        if not singles:
            self._log.warning("detail_structure_unknown", url=url)
            return None

        is_extra = voyage_status == OperationStatusEnum.extra
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
            if is_extra and _SKIPPED_PORT_CLASS in classes:
                # 臨時便が寄らない港には行を作らない。時刻も使わない（research R3。
                # 寄らない港には定期便の時刻や別の日付が残っている）
                continue
            if _SKIPPED_PORT_CLASS in classes:
                # 便全体が欠航・運休のときは抜港ではなく便のステータス（FR-005）
                status = (
                    voyage_status
                    if voyage_status
                    in (OperationStatusEnum.cancelled, OperationStatusEnum.suspended)
                    else OperationStatusEnum.skipped
                )
            else:
                status = self._port_status(classes, is_extra)
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
                if not is_extra:  # 臨時便では寄らない港を by_port に入れない
                    self._log.warning(
                        "detail_stop_missing", url=url, port_id=stop.port_id
                    )
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
                    # 臨時便が書いた行か（同じキーの定期便との優先に使う。research R4）
                    "extra_voyage": is_extra,
                    # 日付で消すと、出港日がずれて同じ日付になった別の便の行まで消えるので使わない（#28）
                    "replace_scope": None,
                    # 同じ便の、今回書かなかった行（予備ルートの行、遅延で前の日付になった行）を消すため
                    # （詳細ページの URL は便ごとに一つ：/service/downstream20260930/。予備ルートの行も同じ URL）
                    # 臨時便は港を決めない（寄らなくなった港の行も消す。research R7）
                    "replace_source": (
                        route.id,
                        None if is_extra else stop.port_id,
                        url,
                    ),
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
                    "extra_voyage": False,
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

    def _voyage_kind(self, block: Tag, url: str | None) -> str:
        """一覧の便の種類："extra"（臨時便）・"regular"（定期便）・"unknown"（分からない）。

        一覧のクラスは実物が未確認なので、fetch() で決めた詳細ページの種類でも見分ける（research R1）。
        詳細ページが取れなかった便は unknown。fetch() を通っていない便は定期便。
        """
        if _EXTRA_CLASS in block.get("class", []):
            return "extra"
        return getattr(self, "_voyage_kinds", {}).get(url or "", "regular")

    @staticmethod
    def _detail_kind(soup: BeautifulSoup) -> str:
        """詳細ページの見出しに【臨時便…】、または寄る港の全部のクラスに temporary があれば "extra"。"""
        h1 = soup.select_one("h1.heading1")
        if h1 is not None and _EXTRA_HEADING in h1.get_text():
            return "extra"
        # 港の temporary は、寄らない港（no_status）を除く全部の港に付くときだけ。
        # 定期便が1港に臨時寄港しただけで、便ごと臨時便にしない（PR #90 レビュー）
        stops = [
            single.get("class", [])
            for single in soup.select("div.service > div.single")
            if _SKIPPED_PORT_CLASS not in single.get("class", [])
        ]
        if stops and all(_EXTRA_CLASS in classes for classes in stops):
            return "extra"
        return "regular"

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

    def _port_status(
        self, classes: list[str], is_extra: bool
    ) -> OperationStatusEnum | None:
        """詳細ページの港のステータス。

        temporary は便の種類で、状態のクラスではない。ほかの状態のクラスが付けばその状態
        （`temporary cancel alert` は cancelled）。付かなければ、臨時便なら extra、
        定期便（1港だけ臨時寄港）なら operating。定期便の港を extra で書くと、次の回の欠航が
        臨時便の行として守られて出なくなる（PR #90 レビュー）。
        `temporary alert`（alert だけ）は extra：詳細ページの港で alert だけの例は確認していない。
        一覧の alert だけは cancelled（2026-03 の一覧）だが、temporary と一緒のときは臨時便を優先する。
        """
        if _EXTRA_CLASS not in classes:
            return self._parse_status_from_classes(classes)
        matched = {s for c, s in _STATUS_BY_CLASS.items() if c in classes}
        if not matched:
            return (
                OperationStatusEnum.extra if is_extra else OperationStatusEnum.operating
            )
        return matched.pop() if len(matched) == 1 else None

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

    def _parse_direction(self, info2_text: str, block: Tag | None = None) -> str | None:
        """方向を決める。出発港 → 一覧の欄 → 行き先の順（research R2）。

        '2026年3月7日 鹿児島新港発...' は下り、'那覇港発...' は上り（今までどおり）。
        名瀬発の臨時便（'名瀬港発 鹿児島新港 向け'）は出発港で決まらないので、一覧の欄
        （div.down_stream_services・div.up_stream_services）か、行き先（'那覇... 向け' → 下り、
        '鹿児島... 向け' → 上り）で決める。
        """
        if re.search(r"鹿児島\S*発", info2_text):
            return "down"
        if re.search(r"那覇\S*発", info2_text):
            return "up"
        if block is not None:
            for parent in block.parents:
                classes = parent.get("class", []) if isinstance(parent, Tag) else []
                if "down_stream_services" in classes:
                    return "down"
                if "up_stream_services" in classes:
                    return "up"
        if re.search(r"那覇\S*\s*向け", info2_text):
            return "down"
        if re.search(r"鹿児島\S*\s*向け", info2_text):
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
