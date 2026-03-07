"""
MarueFerry (マルエーフェリー) scraper.

Target: https://www.aline-ferry.com/status/
Actual HTML structure (confirmed 2026-03-07):
    <div class="status-archive">
      <h3>フェリーあけぼの鹿児島 - 名瀬 - 亀徳 - 和泊 - 与論 - 本部 - 那覇</h3>
      <h4>■3/6(金)下り便…条件付き運航</h4>
      <div class="status-detail">        <!-- 異常時のみ -->
        <div class="tag-list"><span class="tag-conditionally">条件付運航</span></div>
        <p>詳細テキスト...</p>
      </div>
      <p>2026年03月07日更新</p>
    </div>

    通常運航時は status-detail div なし:
      <h4>通常運航致しております。</h4>
      <p>2026年03月07日更新</p>

Status parsing:
    h4 に "…" がある場合: その後ろの文字列からステータスを判定
    h4 に "…" がない場合: h4 全体テキストのキーワードからステータスを判定
    日付がない場合（"通常運航致しております"等）: valid_date = today

Direction:
    h4 に "下り" → 下り便（鹿児島 → 那覇）
    h4 に "上り" → 上り便（那覇 → 鹿児島）
    方向不明     → 上り・下り両方に同じデータを適用

Detail:
    h4 の次の div.status-detail 内の p テキストを使用
"""
import re
from datetime import date, datetime

from bs4 import BeautifulSoup
from sqlalchemy import select

from scraper.db.models import OperationStatusEnum, Route
from scraper.scrapers.base import BaseScraper

SOURCE_URL = "https://www.aline-ferry.com/status/"


class MarueFerry(BaseScraper):
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

        in_scope = False  # 那覇行き航路の h3 セクション内かどうか

        for elem in soup.find_all(["h3", "h4"]):
            if elem.name == "h3":
                in_scope = "那覇" in elem.get_text(strip=True)
                continue

            # h4
            if not in_scope:
                continue

            h4_text = elem.get_text(strip=True)
            valid_date = self._parse_date(h4_text) or date.today()
            status = self._parse_status(h4_text)
            if status is None:
                continue

            direction = self._parse_direction(h4_text)
            if direction == "down":
                target_routes = [down_route] if down_route else []
            elif direction == "up":
                target_routes = [up_route] if up_route else []
            else:
                # 方向不明 → 上り・下り両方に同じ情報を適用
                target_routes = [r for r in [down_route, up_route] if r]

            detail_lines: list[str] = []
            detail_div = elem.find_next_sibling("div", class_="status-detail")
            if detail_div:
                for p in detail_div.find_all("p"):
                    t = p.get_text(strip=True)
                    if t:
                        detail_lines.append(t)
            detail = "\n".join(detail_lines) or None

            for route in target_routes:
                key = (route.id, valid_date)
                if key in seen:
                    continue
                seen.add(key)
                records.append({
                    "route_id": route.id,
                    "status": status,
                    "status_detail": detail,
                    "valid_date": valid_date,
                    "scraped_at": datetime.now(),
                    "source_url": SOURCE_URL,
                })

        # 片方の方向のみ記録がある日付は、もう片方を operating で補完する
        if down_route and up_route:
            dates_down = {r["valid_date"] for r in records if r["route_id"] == down_route.id}
            dates_up = {r["valid_date"] for r in records if r["route_id"] == up_route.id}

            for d in dates_down - dates_up:
                records.append({
                    "route_id": up_route.id,
                    "status": OperationStatusEnum.operating,
                    "status_detail": None,
                    "valid_date": d,
                    "scraped_at": datetime.now(),
                    "source_url": SOURCE_URL,
                })
            for d in dates_up - dates_down:
                records.append({
                    "route_id": down_route.id,
                    "status": OperationStatusEnum.operating,
                    "status_detail": None,
                    "valid_date": d,
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

    def _parse_direction(self, h4_text: str) -> str | None:
        if "下り" in h4_text:
            return "down"
        if "上り" in h4_text:
            return "up"
        return None

    def _parse_date(self, h4_text: str) -> date | None:
        """■3/6(金)下り便… → date(2026, 3, 6)。日付がなければ None。"""
        m = re.search(r"(\d{1,2})[/／](\d{1,2})", h4_text)
        if not m:
            return None
        try:
            today = date.today()
            month, day = int(m.group(1)), int(m.group(2))
            candidate = date(today.year, month, day)
            # 年またぎ対応: 180日以上先なら前年、180日以上前なら翌年
            delta = (candidate - today).days
            if delta > 180:
                candidate = date(today.year - 1, month, day)
            elif delta < -180:
                candidate = date(today.year + 1, month, day)
            return candidate
        except ValueError:
            self._log.warning("date_invalid", text=h4_text[:40])
            return None

    def _parse_status(self, h4_text: str) -> OperationStatusEnum | None:
        """h4 テキストからステータスを判定。"""
        status_part = h4_text.split("…")[-1] if "…" in h4_text else h4_text
        if "欠航" in status_part:
            return OperationStatusEnum.cancelled
        if "条件付" in status_part:
            return OperationStatusEnum.delayed
        if "遅延" in status_part or "スケジュール変更" in status_part:
            return OperationStatusEnum.delayed
        if "運休" in status_part:
            return OperationStatusEnum.suspended
        if "通常" in status_part or "通常運航" in h4_text:
            return OperationStatusEnum.operating
        return None
