"""
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
    すべて freeze_after_departure=True（出港済みの行は確定）、replace_scope=(route, port, date)
"""

from datetime import date, datetime


from scraper.db.models import (
    OperationStatusEnum,
    Route,
)
from scraper.scrapers.marue_ferry.common import (
    SEARCH_URL,
    KAGOSHIMA_URL,
    SEVERITY,
    ShipInfo,
)
from scraper.scrapers.marue_ferry.state import MarueState
from scraper.utils.port_notice import (
    PortNotice,
)


class StatusesMixin(MarueState):
    # ------------------------------------------------------------------
    # 航路単位（operation_statuses）
    # ------------------------------------------------------------------

    def parse(self, html: str) -> list[dict]:
        down_route, up_route = self._routes
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
        stops = self._stops.get(route.id, [])
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
        worst = max(known, key=lambda s: SEVERITY.get(s.status, 0))
        return worst.status, self._ship_detail_text(worst)

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
        self._parse_now = (
            now  # 臨時便の削除（_upsert_departures）も同じ「今」で判断する
        )
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

        records.extend(self._extra_records(records, now))
        self._log.info("parsed_departures", records=len(records))
        return records

    def _upsert_departures(self, records: list[dict]) -> tuple[int, int]:
        """親の更新のあと、取りやめになった臨時便の行を消す（research R6）。"""
        result = super()._upsert_departures(records)
        self._delete_withdrawn_extra_rows(records)
        return result
