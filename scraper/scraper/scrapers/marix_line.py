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

CSS class → status mapping (div.status_single_cover のクラスで判定):
    normal                   → operating
    conditional + alert      → delayed（条件付き）
    alert (conditional なし) → cancelled（欠航）

Direction (div.info2 の出発港で判定):
    "鹿児島" + "発" → 下り（鹿児島 → 那覇）
    "那覇"   + "発" → 上り（那覇 → 鹿児島）

Date: div.info2 の最初の "YYYY年M月D日" を valid_date として使用
"""
import re
from datetime import date, datetime

from bs4 import BeautifulSoup
from sqlalchemy import select

from scraper.db.models import OperationStatusEnum, Route
from scraper.scrapers.base import BaseScraper

SOURCE_URL = "https://marixline.com/service/"


class MarixLine(BaseScraper):
    def fetch(self) -> str:
        resp = self.http.get(SOURCE_URL, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
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

            status = self._parse_status_from_classes(cls)
            if status is None:
                self._log.debug("unknown_status_class", classes=cls)
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

            exp = block.find("p", class_="exp")
            exp_text = exp.get_text(strip=True) if exp else None
            detail = exp_text if status != OperationStatusEnum.operating else None

            records.append({
                "route_id": route.id,
                "status": status,
                "status_detail": detail,
                "valid_date": valid_date,
                "scraped_at": datetime.now(),
                "source_url": SOURCE_URL,
            })

        # 今日の便が存在しないルートに no_service を記録
        today = date.today()
        for route in [r for r in [down_route, up_route] if r]:
            if (route.id, today) not in seen:
                records.append({
                    "route_id": route.id,
                    "status": OperationStatusEnum.no_service,
                    "status_detail": None,
                    "valid_date": today,
                    "scraped_at": datetime.now(),
                    "source_url": SOURCE_URL,
                })

        self._log.info("parsed", records=len(records))
        return records

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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

    def _parse_status_from_classes(self, classes: list[str]) -> OperationStatusEnum | None:
        if "normal" in classes:
            return OperationStatusEnum.operating
        if "conditional" in classes and "alert" in classes:
            return OperationStatusEnum.delayed
        if "alert" in classes:
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
