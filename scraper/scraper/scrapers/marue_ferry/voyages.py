"""
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
"""

from dataclasses import replace
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from scraper.db.models import (
    DepartureStatus,
    OperationStatusEnum,
)
from scraper.scrapers.marue_ferry.common import (
    _SEARCH_ROWS,
    _SEVERITY,
    _SAME_VOYAGE,
    SearchRow,
    VoyageStatus,
    ShipInfo,
    RecordedVoyage,
)
from scraper.scrapers.marue_ferry.state import MarueState
from scraper.utils.port_notice import (
    PortNotice,
    extract_notice_text,
    extract_port_notices,
)


class VoyagesMixin(MarueState):
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
        departure_date = self._departure_date(route_id, cur[1], port_id)
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
                _SEARCH_ROWS,
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

        accepted = list(searched)
        result: list[tuple[str, int, datetime]] = []
        for r in rows:
            if any(
                ship == r.ship_name
                and route_id == r.route_id
                and abs(arrival - r.scheduled_arrival_at) < _SAME_VOYAGE
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
        if ship is None or not ship.voyages or row.arrival_at is None:
            return None, None
        origin_date = self._departure_date(route_id, row.arrival_at)
        if origin_date is None:
            return None, None
        line = self._voyage_line(ship, route_id, origin_date, row.arrival_at.date())
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
        origin_date = self._departure_date(route_id, arrival_at)
        if origin_date is None:
            return ship
        return self._for_voyage(ship, route_id, origin_date, arrival_at)

    def _departure_date(
        self, route_id: int, arrival_at: datetime, port_id: int | None = None
    ) -> date | None:
        """下船日時の便が、port_id の港（省略すれば始発港）を出る日。

        出港日 ＝ 下船日 −（終点の day_offset − その港の day_offset）。航路や港が分からなければ None。
        """
        stops = self._get_stops().get(route_id, [])
        start = (
            stops[0]
            if port_id is None and stops
            else next((s for s in stops if s.port_id == port_id), None)
        )
        if start is None:
            return None
        return arrival_at.date() - timedelta(
            days=stops[-1].day_offset - start.day_offset
        )

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
                    DepartureStatus.scheduled_arrival_at > arrival_at - _SAME_VOYAGE,
                    DepartureStatus.scheduled_arrival_at < arrival_at + _SAME_VOYAGE,
                    _SEARCH_ROWS,
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
