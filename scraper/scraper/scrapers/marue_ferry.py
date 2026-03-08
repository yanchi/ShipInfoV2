"""
MarueFerry (マルエーフェリー) scraper.

2ステップ取得方式:
  Step 1: POST https://www.aline-ferry.com/search/result.php
          startDate=YYYY-MM-DD, startPort=50, endPort=83
          → table.s-result tbody tr が1行以上あれば「本日便あり」
  Step 2: GET https://www.aline-ferry.com/kagoshima/
          div.ferry-name で船ブロックを特定し、span(tag-list内) からステータスを取得
          上り・下り両ルートに同じステータスを適用

HTML構造（鹿児島ページ、確認済み 2026-03-08）:
    <a href="...">
      <div class="route-head">
        <div class="ferry-name">フェリーあけぼの</div>
        <div class="route-detail">鹿児島 - 名瀬 - ...</div>
      </div>
      <div class="tag-list">
        <span class="tag-normal">通常運航</span>
      </div>
      <div class="situation-excerpt">通常運航致しております。</div>
    </a>

raw_html_hash: 鹿児島ページの HTML で計算（便なし時は空文字列 → SHA-256("")）
valid_date: 常に date.today()（POST の startDate と同値）
便なし時: OperationStatusEnum.no_service を記録（cancelled とは別。便が設定されていない日）
"""
from datetime import date, datetime

from bs4 import BeautifulSoup
from sqlalchemy import select

from scraper.db.models import OperationStatusEnum, Route
from scraper.scrapers.base import BaseScraper

SEARCH_URL = "https://www.aline-ferry.com/search/result.php"
KAGOSHIMA_URL = "https://www.aline-ferry.com/kagoshima/"


class MarueFerry(BaseScraper):
    def __init__(self, session, company_id: int) -> None:
        # Step 1 POSTs are read-only search queries (no side effects),
        # so enable POST retries on 429/5xx.
        super().__init__(session, company_id, retry_post=True)

    def fetch(self) -> str:
        self._has_service = True
        self._valid_date = date.today()

        # Step 1: 本日便の有無を確認
        today_str = self._valid_date.isoformat()
        resp = self.http.post(
            SEARCH_URL,
            data={"startDate": today_str, "startPort": "50", "endPort": "83"},
            timeout=30,
        )
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        search_soup = BeautifulSoup(resp.text, "lxml")
        self._has_service = self._check_service(search_soup)

        if not self._has_service:
            self._log.info("no_service_today", date=today_str)
            return ""

        # Step 2: 鹿児島航路ページからステータス詳細を取得
        resp2 = self.http.get(KAGOSHIMA_URL, timeout=30)
        resp2.raise_for_status()
        resp2.encoding = resp2.apparent_encoding
        return resp2.text

    def parse(self, html: str) -> list[dict]:
        down_route, up_route = self._load_routes()
        if down_route is None:
            self._log.warning("route_not_found", direction="down")
        if up_route is None:
            self._log.warning("route_not_found", direction="up")
        valid_date = getattr(self, "_valid_date", date.today())
        routes = [r for r in [down_route, up_route] if r]
        records: list[dict] = []

        if not getattr(self, "_has_service", True):
            # 本日便なし → 上り・下り両ルートを no_service で記録
            for route in routes:
                records.append({
                    "route_id": route.id,
                    "status": OperationStatusEnum.no_service,
                    "status_detail": None,
                    "valid_date": valid_date,
                    "scraped_at": datetime.now(),
                    "source_url": SEARCH_URL,
                })
            self._log.info("parsed_no_service", records=len(records))
            return records

        # 鹿児島ページを解析: 全船のステータスを収集して最悪値を採用
        # 構造: a > div.route-head > div.ferry-name / div.tag-list > span / div.situation-excerpt
        soup = BeautifulSoup(html, "lxml")
        ship_statuses: list[tuple] = []

        for ferry_name_div in soup.find_all("div", class_="ferry-name"):
            block = ferry_name_div.find_parent("a")
            if block is None:
                continue
            tag_span = block.select_one("div.tag-list span")
            if tag_span is None:
                self._log.warning("tag_span_not_found", ship=ferry_name_div.get_text(strip=True))
                continue

            status_text = tag_span.get_text(strip=True)
            status = self._parse_status_text(status_text)
            if status is None:
                self._log.warning("unknown_status_text", ship=ferry_name_div.get_text(strip=True), text=status_text[:60])
                continue

            excerpt_div = block.find("div", class_="situation-excerpt")
            detail = excerpt_div.get_text(strip=True) if excerpt_div else None
            if not detail:
                detail = None
            if status == OperationStatusEnum.operating:
                detail = None
            ship_statuses.append((status, detail))

        if not ship_statuses:
            self._log.error("no_records_parsed", html_len=len(html))
            raise RuntimeError("MarueFerry.parse: no ship statuses parsed (possible site structure change)")

        # 複数船で異なるステータスがある場合は最も深刻なものを採用して warning
        _SEVERITY = {
            OperationStatusEnum.cancelled: 4,
            OperationStatusEnum.suspended: 3,
            OperationStatusEnum.delayed: 2,
            OperationStatusEnum.operating: 1,
        }
        unique_statuses = {s for s, _ in ship_statuses}
        if len(unique_statuses) > 1:
            self._log.warning("mixed_ship_statuses", statuses=[s.value for s in unique_statuses])
        chosen_status, chosen_detail = max(ship_statuses, key=lambda x: _SEVERITY.get(x[0], 0))

        for route in routes:
            records.append({
                "route_id": route.id,
                "status": chosen_status,
                "status_detail": chosen_detail,
                "valid_date": valid_date,
                "scraped_at": datetime.now(),
                "source_url": KAGOSHIMA_URL,
            })

        self._log.info("parsed", records=len(records))
        return records

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_service(self, soup: BeautifulSoup) -> bool:
        """table.s-result の tbody に tr が1行以上あれば本日便あり。
        table.s-result 自体が見つからない場合はサイト構造変更とみなし、
        警告を出したうえで「本日便あり」（安全側）と判定する。
        """
        table = soup.select_one("table.s-result")
        if table is None:
            self._log.warning("result_table_missing")
            return True
        return bool(table.select("tbody tr"))

    def _load_routes(self) -> tuple:
        """(down_route, up_route) を返す。origin_port で判定。"""
        routes = self.session.execute(
            select(Route).where(
                Route.ferry_company_id == self.company_id,
                Route.active.is_(True),
            )
        ).scalars().all()
        down = next((r for r in routes if r.origin_port == "鹿児島"), None)
        up = next((r for r in routes if r.origin_port == "那覇"), None)
        return down, up

    def _parse_status_text(self, text: str) -> OperationStatusEnum | None:
        """鹿児島ページの div.tag-list 内の span テキストからステータスを判定。"""
        if "欠航" in text:
            return OperationStatusEnum.cancelled
        if "条件付" in text:
            return OperationStatusEnum.delayed
        if "遅延" in text or "スケジュール変更" in text:
            return OperationStatusEnum.delayed
        if "運休" in text:
            return OperationStatusEnum.suspended
        if "通常" in text:
            return OperationStatusEnum.operating
        return None
