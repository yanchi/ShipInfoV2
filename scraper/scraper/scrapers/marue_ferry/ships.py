"""マルエーフェリーの一覧・船の詳細ページの読み取り。"""

import re
from datetime import date

from bs4 import BeautifulSoup

from scraper.db.models import (
    OperationStatusEnum,
)
from scraper.scrapers.marue_ferry.common import (
    SEVERITY,
    CONDITIONAL_WORDS,
    VoyageStatus,
    ShipInfo,
    VOYAGE_LINE,
    VOYAGE_STATUS_END,
    nearest_date,
)
from scraper.scrapers.marue_ferry.state import MarueState


class ShipsMixin(MarueState):
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
            max((st for _, st in known), key=lambda s: SEVERITY.get(s, 0))
            if known
            else None
        )
        conditional = any(w in t for t, _ in known for w in CONDITIONAL_WORDS)
        schedule_changed = any("遅延" in t or "スケジュール変更" in t for t, _ in known)
        return status, conditional, schedule_changed

    def _parse_voyages(self, excerpt: str) -> tuple[VoyageStatus, ...]:
        """抜粋の便ごとの行を読む。年は今日にいちばん近い日付になる年。"""
        today = getattr(self, "_valid_date", None) or date.today()
        voyages: list[VoyageStatus] = []
        for m in VOYAGE_LINE.finditer(excerpt):
            departure_date = nearest_date(
                int(m.group("month")), int(m.group("day")), today
            )
            if departure_date is None:
                continue
            # 状態の語だけを見る。補足（「（与論港は欠航の可能性あり）」「※…欠航となる場合が…」）は捨てる
            words = VOYAGE_STATUS_END.split(m.group("status"), maxsplit=1)[0]
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
        """日付と方向の間の文字列の出発港が、その方向の航路の途中の港か。"""
        # 「発」があれば最後の「発」より前、無ければ方向の手前の全部。最後に出てくる港が出発港
        # （「名瀬経由 那覇港発」のように先に別の港名があっても、発の港を取る）
        head = place.rpartition("発")[0] if "発" in place else place
        occurrences = self._get_resolver().find_occurrences(head)
        if not occurrences:
            return False
        port = occurrences[-1][2]
        route_id = next(
            (
                rid
                for rid, label in self._route_directions().items()
                if label == direction
            ),
            None,
        )
        stops = self._stops.get(route_id, [])
        return any(s.port_id == port.id for s in stops[1:-1])

    def _parse_status_text(self, text: str) -> OperationStatusEnum | None:
        """鹿児島ページの div.tag-list 内の span テキストからステータスを判定。"""
        if "欠航" in text:
            return OperationStatusEnum.cancelled
        if any(w in text for w in CONDITIONAL_WORDS):
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
