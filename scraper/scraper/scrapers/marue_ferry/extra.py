"""
臨時便（12-marue-extra-voyages）:
    船の詳細ページの div.status-archive の【臨時便(上り/下り)】（次の【…】・《…》まで）を fetch() で読む（_parse_extra_voyages）
    - 読めない臨時便（曜日違い・航路に無い港・順番違い・出港なし・終点の入港なし・時刻が戻る）は警告
      extra_voyage_unreadable を出して作らず、その船はこの回の削除の対象から外す（ExtraParse.complete）
    - 出港時刻のある港ごとに、状態 extra の行を作る（終点の行は作らない）。今日〜MARUE_SEARCH_DAYS_AHEAD 日先だけ。
      抜粋に同じ臨時便の行（始発港から書いた・日付が始発港の出港日と同じ）が欠航・運休・条件付ならその状態と抜粋の文
    - 臨時便の行の目印は source_url（船の詳細ページの URL）。状態では見分けない。便検索から作る行は SEARCH_URL。
      定期便の今の便・出港済み・前回の記録・2日先以降の検索間隔は、DB を読むとき SEARCH_ROWS で臨時便の行を除く
    - 便検索の行と同じキー（航路・港・出港日・船）は便検索を優先して作らない。出港時刻が違えば便検索の行の詳細に
      「臨時便 HH:MM発あり」を足す（extra_voyage_key_conflict）
    - 臨時便の告知は港別情報に使わない（utils/port_notice.py の _detail_body が読み飛ばす）
    - 告知から消えた臨時便の行は _upsert_departures() で消す。始発港の行があり、その出港が今より後の便だけ
      （出港済みの便・始発港の行が無い便は残す）。replace_scope は付けない（便検索の整理で消えないように）
"""

from dataclasses import replace
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup
from sqlalchemy import func, select

from scraper.config import settings
from scraper.db.models import (
    DepartureStatus,
    OperationStatusEnum,
)
from scraper.scrapers.marue_ferry.common import (
    SEARCH_URL,
    SEARCH_ROWS,
    SAME_VOYAGE,
    ExtraStop,
    ExtraVoyage,
    ExtraParse,
    EXTRA_HEADING,
    EXTRA_STOP,
    EXTRA_TIME_PART,
    EXTRA_SKIP_NOTE,
    WEEKDAYS,
    nearest_date,
    iso,
)
from scraper.scrapers.marue_ferry.state import MarueState


class ExtraMixin(MarueState):
    # ------------------------------------------------------------------
    # 臨時便（船の詳細ページの【臨時便】。specs/12-marue-extra-voyages）
    # ------------------------------------------------------------------

    def _extra_records(self, records: list[dict], now: datetime) -> list[dict]:
        """臨時便の出港時刻のある港ごとに行を作る（data-model「行の作り方」）。

        便検索の行とキー（航路・港・出港日・船名）がぶつかるときは便検索を優先し、作らない。
        """
        extra = getattr(self, "_extra_voyages", None) or {}
        today = getattr(self, "_valid_date", None) or date.today()
        last = today + timedelta(days=settings.marue_search_days_ahead)
        by_key = {
            (r["route_id"], r["port_id"], r["departure_date"], r["ship_name"]): r
            for r in records
        }
        result: list[dict] = []
        seen: set[tuple] = set()
        for ship_name, parsed in extra.items():
            if parsed is None:
                continue
            for voyage in parsed.voyages:
                status, detail = self._extra_status(voyage, records)
                recorded = self._recorded_search_keys_of(voyage, today, last)
                self._warn_extra_arrival_changed(voyage)
                skips = self._extra_skips_after(voyage)
                for stop, skips_after in zip(voyage.stops[:-1], skips):
                    departure_at = stop.departure_at
                    key = (
                        voyage.route_id,
                        stop.port_id,
                        departure_at.date(),
                        ship_name,
                    )
                    if not today <= key[2] <= last:
                        continue
                    searched = by_key.get(key)
                    if searched is not None:
                        self._note_extra_conflict(searched, voyage, departure_at)
                        continue
                    if key[1:3] in recorded:
                        continue
                    if key in seen:
                        # 同じ船・港・出港日に臨時便が2本。キーは1つしか持てないので先の1本だけ作る
                        self._log.warning(
                            "extra_voyage_duplicate_key",
                            ship=ship_name,
                            route_id=key[0],
                            port_id=key[1],
                            date=str(key[2]),
                            skipped_departure=iso(departure_at),
                        )
                        continue
                    seen.add(key)
                    result.append(
                        {
                            "route_id": key[0],
                            "port_id": key[1],
                            "departure_date": key[2],
                            "ship_name": ship_name,
                            "status": status,
                            "status_detail": detail,
                            "scheduled_departure_at": departure_at,
                            "scheduled_arrival_at": voyage.stops[-1].arrival_at,
                            "operated_by_company_id": None,
                            "source_url": self._ships[ship_name].detail_url,
                            "skips_ports_after": skips_after,
                            "freeze_after_departure": True,
                        }
                    )
        return result

    def _extra_skips_after(self, voyage: ExtraVoyage) -> list[bool]:
        """終点以外の港ごとに、その港を出たあと終点までに臨時便が寄らない港があるか（16-extra-skip-flag R2）。

        寄らない港は、航路の寄港順にあって【臨時便】の並びに無い港。並びは寄港順に読んでいる（_build_extra_voyage）。
        便検索とぶつかって行を作らない港も並びにあるので寄港に数える。
        """
        order = [s.port_id for s in self._stops.get(voyage.route_id, [])]
        called = {s.port_id for s in voyage.stops}
        last = order.index(voyage.stops[-1].port_id)
        return [
            any(p not in called for p in order[order.index(stop.port_id) + 1 : last])
            for stop in voyage.stops[:-1]
        ]

    def _warn_extra_arrival_changed(self, voyage: ExtraVoyage) -> None:
        """終点の入港時刻が変わると、同じ臨時便が別の便（scheduled_arrival_at 違い）として2組に分かれる（R6 の既知の取りこぼし）。"""
        arrival = voyage.stops[-1].arrival_at
        before = self.session.execute(
            select(func.min(DepartureStatus.scheduled_arrival_at)).where(
                DepartureStatus.ship_name == voyage.ship_name,
                DepartureStatus.route_id == voyage.route_id,
                DepartureStatus.source_url == self._ships[voyage.ship_name].detail_url,
                DepartureStatus.scheduled_arrival_at != arrival,
                DepartureStatus.scheduled_arrival_at > arrival - SAME_VOYAGE,
                DepartureStatus.scheduled_arrival_at < arrival + SAME_VOYAGE,
            )
        ).scalar()
        if before is not None:
            self._log.warning(
                "extra_voyage_arrival_changed",
                ship=voyage.ship_name,
                route_id=voyage.route_id,
                before=iso(before),
                after=iso(arrival),
            )

    def _delete_withdrawn_extra_rows(self, records: list[dict]) -> None:
        """告知から消えた臨時便の行を、始発港を出る前の便だけ消す（FR-008）。

        対象は、この回に詳細ページを取れて読めない臨時便が無かった船だけ。便（船・航路・終点の入港時刻）ごとに、
        始発港の行があり、その出港が今より後で、出港日が今日〜MARUE_SEARCH_DAYS_AHEAD 日先の範囲にある
        今回書かなかったキーの行を消す。始発港の行が無い便は出港済みとみなして残す（消すより残すほうが安全）。
        """
        extra = getattr(self, "_extra_voyages", None) or {}
        now = getattr(self, "_parse_now", None) or datetime.now()
        today = getattr(self, "_valid_date", None) or date.today()
        last = today + timedelta(days=settings.marue_search_days_ahead)
        route_ids = [r.id for r in self._routes if r]
        origins = {rid: stops[0].port_id for rid, stops in self._stops.items() if stops}
        written = {
            (r["route_id"], r["port_id"], r["departure_date"], r["ship_name"])
            for r in records
        }
        for ship_name, parsed in extra.items():
            if parsed is None or not parsed.complete or not route_ids:
                continue
            rows = (
                self.session.execute(
                    select(DepartureStatus).where(
                        DepartureStatus.ship_name == ship_name,
                        DepartureStatus.route_id.in_(route_ids),
                        DepartureStatus.source_url.is_not(None),
                        DepartureStatus.source_url != SEARCH_URL,
                        DepartureStatus.scheduled_arrival_at > now,
                        DepartureStatus.scheduled_departure_at.is_not(None),
                    )
                )
                .scalars()
                .all()
            )
            voyages: dict[tuple[int, datetime], list[DepartureStatus]] = {}
            for row in rows:
                voyages.setdefault((row.route_id, row.scheduled_arrival_at), []).append(
                    row
                )
            deleted = 0
            for (route_id, _), group in voyages.items():
                if not any(r.port_id == origins.get(route_id) for r in group):
                    continue
                if min(r.scheduled_departure_at for r in group) <= now:
                    continue
                for row in group:
                    key = (row.route_id, row.port_id, row.departure_date, ship_name)
                    if today <= row.departure_date <= last and key not in written:
                        self.session.delete(row)
                        deleted += 1
            if deleted:
                self._log.info(
                    "extra_voyage_rows_deleted", ship=ship_name, count=deleted
                )

    def _extra_status(
        self, voyage: ExtraVoyage, records: list[dict]
    ) -> tuple[OperationStatusEnum, str | None]:
        """臨時便の行の状態（R4）。抜粋に合う行が欠航・運休・条件付ならそれ、それ以外は extra。

        合う行は、始発港から書いた（from_midway でない）、方向が同じで日付が始発港の出港日と同じ行だけ。
        同じ船・始発港の出港日の定期便が便検索にあるときは、抜粋の行は定期便のものとみなして当てない。
        """
        ship = self._ships.get(voyage.ship_name)
        extra = (OperationStatusEnum.extra, voyage.skip_note)
        if ship is None or not ship.voyages:
            return extra
        origin_date = voyage.stops[0].departure_at.date()
        direction = self._route_directions().get(voyage.route_id)
        line = next(
            (
                v
                for v in ship.voyages
                if v.direction == direction
                and not v.from_midway
                and v.departure_date == origin_date
            ),
            None,
        )
        if line is None or line.status not in (
            OperationStatusEnum.cancelled,
            OperationStatusEnum.suspended,
            OperationStatusEnum.delayed,
        ):
            return extra
        if self._has_regular_voyage(voyage, origin_date, records):
            return extra
        return line.status, self._ship_detail_text(replace(ship, status=line.status))

    def _has_regular_voyage(
        self, voyage: ExtraVoyage, origin_date: date, records: list[dict]
    ) -> bool:
        """同じ船・航路・始発港の出港日の定期便（便検索の行）が、この回の記録か DB にあるか。"""
        for r in records:
            arrival = r.get("scheduled_arrival_at")
            if (
                r["ship_name"] == voyage.ship_name
                and r["route_id"] == voyage.route_id
                and arrival is not None
                and self._departure_date(voyage.route_id, arrival) == origin_date
            ):
                return True
        stops = self._stops.get(voyage.route_id, [])
        if not stops:
            return False
        arrival_date = origin_date + timedelta(
            days=stops[-1].day_offset - stops[0].day_offset
        )
        start = datetime(arrival_date.year, arrival_date.month, arrival_date.day)
        return (
            self.session.execute(
                select(DepartureStatus.id)
                .where(
                    DepartureStatus.ship_name == voyage.ship_name,
                    DepartureStatus.route_id == voyage.route_id,
                    SEARCH_ROWS,
                    DepartureStatus.scheduled_arrival_at >= start,
                    DepartureStatus.scheduled_arrival_at < start + timedelta(days=1),
                )
                .limit(1)
            ).first()
            is not None
        )

    def _recorded_search_keys_of(
        self, voyage: ExtraVoyage, first: date, last: date
    ) -> set[tuple[int, date]]:
        """DB にある、この船・航路の便検索の行の (port_id, 出港日)（この回に検索しなかったキーを含む。R7）。"""
        rows = self.session.execute(
            select(DepartureStatus.port_id, DepartureStatus.departure_date).where(
                DepartureStatus.ship_name == voyage.ship_name,
                DepartureStatus.route_id == voyage.route_id,
                SEARCH_ROWS,
                DepartureStatus.departure_date >= first,
                DepartureStatus.departure_date <= last,
            )
        ).all()
        return {(r.port_id, r.departure_date) for r in rows}

    def _note_extra_conflict(
        self, searched: dict, voyage: ExtraVoyage, departure_at: datetime
    ) -> None:
        """便検索の記録に出港時刻があり臨時便と違えば、別の便として詳細の後ろに知らせる（R7）。"""
        recorded_at = searched.get("scheduled_departure_at")
        if recorded_at is None or recorded_at == departure_at:
            return
        note = f"臨時便 {departure_at:%H:%M}発あり"
        detail = searched.get("status_detail")
        searched["status_detail"] = f"{detail}（{note}）" if detail else note
        self._log.warning(
            "extra_voyage_key_conflict",
            ship=voyage.ship_name,
            route_id=voyage.route_id,
            port_id=searched["port_id"],
            date=str(searched["departure_date"]),
            search_departure=iso(recorded_at),
            extra_departure=iso(departure_at),
        )

    def _parse_extra_voyages(
        self, detail_html: str | None, ship_name: str
    ) -> ExtraParse | None:
        """船の詳細ページの【臨時便(上り/下り)】を読む（research R1〜R3）。

        詳細ページが無い・status-archive が無ければ None。読めない臨時便は警告を出して入れず、
        complete を False にする（前回作った行を、読めなかったことを理由に消さないため）。
        """
        if not detail_html:
            return None
        archive = BeautifulSoup(detail_html, "lxml").select_one("div.status-archive")
        if archive is None:
            return None

        # (見出し, 方向, 行) の列にする。次の【…】・《…》の行で臨時便を閉じる
        blocks: list[tuple[str, str, list[str]]] = []
        current: tuple[str, str, list[str]] | None = None
        for p in archive.find_all("p"):
            text = p.get_text(" ", strip=True).replace("\xa0", " ").strip()
            heading = EXTRA_HEADING.match(text)
            if heading:
                current = (text, heading.group("direction"), [])
                blocks.append(current)
            elif text.startswith(("【", "《")):
                current = None
            elif current is not None:
                current[2].append(text)

        voyages: list[ExtraVoyage] = []
        complete = True
        for heading, direction, lines in blocks:
            voyage = self._build_extra_voyage(ship_name, heading, direction, lines)
            if voyage is None:
                complete = False
            else:
                voyages.append(voyage)
        return ExtraParse(tuple(voyages), complete)

    def _build_extra_voyage(
        self, ship_name: str, heading: str, direction: str, lines: list[str]
    ) -> ExtraVoyage | None:
        """臨時便1つの行 → ExtraVoyage。読めなければ警告を出して None。"""
        route_id = next(
            (
                rid
                for rid, label in self._route_directions().items()
                if label == direction
            ),
            None,
        )
        order = {s.port_id: i for i, s in enumerate(self._stops.get(route_id, []))}

        def unreadable(line: str) -> None:
            self._log.warning(
                "extra_voyage_unreadable", ship=ship_name, heading=heading, line=line
            )

        if route_id is None:
            unreadable("")
            return None
        today = getattr(self, "_valid_date", None) or date.today()
        stops: list[ExtraStop] = []
        skip_note: str | None = None
        last_order = -1
        last_time: datetime | None = None
        for line in lines:
            if not line:
                continue
            if line.startswith("※"):
                if EXTRA_SKIP_NOTE.search(line):
                    skip_note = line
                continue
            m = EXTRA_STOP.match(line)
            day = (
                nearest_date(int(m.group("month")), int(m.group("day")), today)
                if m
                else None
            )
            port = self._get_resolver().resolve(m.group("port")) if m else None
            if (
                m is None
                or day is None
                or WEEKDAYS[day.weekday()] != m.group("weekday")
                or port is None
                or order.get(port.id, -1) <= last_order
            ):
                unreadable(line)
                return None
            times = {
                kind: datetime(day.year, day.month, day.day, int(h), int(mi))
                for h, mi, kind in EXTRA_TIME_PART.findall(m.group("times"))
            }
            arrival, departure = times.get("入港"), times.get("出港")
            if (
                (arrival is not None and last_time is not None and arrival < last_time)
                or (
                    departure is not None
                    and departure < (arrival or last_time or departure)
                )
                or (not stops and arrival is not None)
                or (stops and arrival is None)
            ):
                unreadable(line)
                return None
            stops.append(ExtraStop(port.id, arrival, departure))
            last_order = order[port.id]
            last_time = departure or arrival

        # 始発港は出港だけ、途中は入港と出港、終点は入港だけ
        if (
            len(stops) < 2
            or stops[0].departure_at is None
            or stops[-1].departure_at is not None
            or any(s.departure_at is None for s in stops[1:-1])
        ):
            unreadable(lines[-1] if lines else "")
            return None
        return ExtraVoyage(ship_name, route_id, tuple(stops), skip_note)
