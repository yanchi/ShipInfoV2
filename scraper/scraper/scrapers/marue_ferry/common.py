"""マルエーフェリーの URL・定数・dataclass・正規表現・モジュール関数。"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import or_

from scraper.db.models import (
    DepartureStatus,
    OperationStatusEnum,
)

# marue_ferry パッケージの中で共有する名前（パッケージの外からは __init__.py の名前を使う）
__all__ = [
    "SEARCH_URL",
    "KAGOSHIMA_URL",
    "SEARCH_ROWS",
    "SEVERITY",
    "SAME_VOYAGE",
    "CONDITIONAL_WORDS",
    "SearchRow",
    "VoyageStatus",
    "ShipInfo",
    "RecordedVoyage",
    "ExtraStop",
    "ExtraVoyage",
    "ExtraParse",
    "VOYAGE_LINE",
    "VOYAGE_STATUS_END",
    "EXTRA_HEADING",
    "EXTRA_TIME",
    "EXTRA_STOP",
    "EXTRA_TIME_PART",
    "EXTRA_SKIP_NOTE",
    "WEEKDAYS",
    "nearest_date",
    "parse_search_datetime",
    "iso_or_none",
]

SEARCH_URL = "https://www.aline-ferry.com/search/result.php"

KAGOSHIMA_URL = "https://www.aline-ferry.com/kagoshima/"

# 便検索から作った行（臨時便の行は source_url が船の詳細ページ。便の判定には混ぜない。research R5）
SEARCH_ROWS = or_(
    DepartureStatus.source_url.is_(None), DepartureStatus.source_url == SEARCH_URL
)

# 船ステータスの重さ（検索に失敗したときの安全側の判定に使う）
SEVERITY = {
    OperationStatusEnum.cancelled: 4,
    OperationStatusEnum.suspended: 3,
    OperationStatusEnum.delayed: 2,
    OperationStatusEnum.operating: 1,
}

# 同じ船・同じ航路で下船日時の差がこれ未満なら同じ便とみなす（1往復に2日以上かかるので、同じ航路を1日に2回走ることはない）
SAME_VOYAGE = timedelta(hours=24)

# 条件付（delayed）として読むタグ・便の行の語。「寄港地変更」は「港変更」を含まない（寄・港・地・変・更）
CONDITIONAL_WORDS = ("条件付", "港変更", "寄港地変更", "抜港")


@dataclass(frozen=True)
class SearchRow:
    """便検索の結果1行。"""

    ship_name: str
    company_name: str
    is_other_company: bool
    departure_at: datetime | None
    arrival_at: datetime | None


@dataclass(frozen=True)
class VoyageStatus:
    """抜粋の便ごとの行（「■10月20日(火)那覇発上り便…条件付き運航・寄港地変更」）。"""

    departure_date: date  # 始発港の出港日
    direction: str  # 「上り」「下り」
    status: OperationStatusEnum
    conditional: bool
    schedule_changed: bool
    # 途中の港から書いた行（「■10月22日(木)名瀬発下り便…」）か。この行だけ出港日〜到着日の範囲で照合する（R7）
    from_midway: bool = False


@dataclass(frozen=True)
class ShipInfo:
    """鹿児島航路ページの船ブロック1つ。status は判定できなければ None。"""

    name: str
    status: OperationStatusEnum | None
    excerpt: str | None
    detail_url: str | None
    # どれかのタグが「条件付」か。遅延・スケジュール変更も status は delayed になるので区別する（FR-006）
    conditional: bool = False
    # どれかのタグが「遅延」「スケジュール変更」か（言及の無い港も時刻が変わっている）
    schedule_changed: bool = False
    # 抜粋の便ごとの状態（書き方が違って読めなければ空）
    voyages: tuple[VoyageStatus, ...] = ()
    # 今の便に合う行が無く、出港前なので通常運航とみなした（FR-011）。港別情報は当てない
    assumed_operating: bool = False
    # 今の便に合う行が無く、出港済みなので前回記録したステータスに戻す（R7）。港別情報は当てない
    use_recorded: bool = False
    # use_recorded のうち、タグのほうが行より重い（行の無い便の変更かもしれない）。
    # まだ出港していない港は記録でなくタグ＋港別情報で決める
    tag_over_recorded: bool = False


@dataclass(frozen=True)
class RecordedVoyage:
    """前回までに記録した、ある便の行（departure_statuses）。"""

    # (port_id, 出港日) → (status, status_detail)。status が NULL の行（運航予定）は入れない
    ports: dict[tuple[int, date], tuple[OperationStatusEnum, str | None]]
    # 記録した出港時刻（始発港の検索が失敗した回でも出港済みか分かるように）
    departures: tuple[datetime, ...]
    # skipped・unknown を除いた、一番重いステータス
    worst: OperationStatusEnum | None
    # worst を取った行の status_detail（今の抜粋は他の便の話なので使わない）
    worst_detail: str | None = None


@dataclass(frozen=True)
class ExtraStop:
    """臨時便の1港。始発港は arrival_at が、終点は departure_at が None。"""

    port_id: int
    arrival_at: datetime | None
    departure_at: datetime | None


@dataclass(frozen=True)
class ExtraVoyage:
    """船の詳細ページの【臨時便(上り/下り)】1つ。stops は本文の順で、最後が終点（入港だけ）。"""

    ship_name: str
    route_id: int
    stops: tuple[ExtraStop, ...]
    # 「※ …寄港いたしません。」の文（行の詳細に使う）
    skip_note: str | None


@dataclass(frozen=True)
class ExtraParse:
    """船ごとの臨時便の読み取り結果。complete が False なら読めない臨時便があった（その船の行は消さない）。"""

    voyages: tuple[ExtraVoyage, ...]
    complete: bool


# 抜粋の便ごとの行。「■10月20日(火)那覇発上り便…条件付き運航・寄港地変更」
# 「10/5(月)鹿児島新港18:00発／下り便…スケジュール変更・条件付運航」。次の行の日付の手前まで
VOYAGE_LINE = re.compile(
    r"(?P<month>\d{1,2})(?:月|/)(?P<day>\d{1,2})日?\s*[(（][^)）]*[)）]"
    r"(?P<place>[^…■]*?)(?P<direction>上り|下り)便?\s*(?:…|\.{3})+\s*"
    r"(?P<status>.+?)(?=■|\d{1,2}(?:月|/)\d{1,2}日?\s*[(（]|$)",
    re.S,
)

# 便の行の状態の語の終わり（この手前までが「条件付き運航・寄港地変更」）
VOYAGE_STATUS_END = re.compile(r"[（(※。\s]")

# 船の詳細ページの臨時便。「【臨時便(下り)】」で始まり、次の【…】・《…》・終わりで閉じる
EXTRA_HEADING = re.compile(r"^【臨時便[(（](?P<direction>上り|下り)[)）]】$")

EXTRA_TIME = r"\d{1,2}:\d{2}[(（](?:入港|出港)[)）]"

EXTRA_STOP = re.compile(
    r"^(?P<month>\d{1,2})月(?P<day>\d{1,2})日[(（](?P<weekday>[日月火水木金土])[)）]"
    r"\s*(?P<port>[^\s\d]+?)\s*(?P<times>" + EXTRA_TIME + "(?:/" + EXTRA_TIME + ")?)$"
)

EXTRA_TIME_PART = re.compile(r"(\d{1,2}):(\d{2})[(（](入港|出港)[)）]")

EXTRA_SKIP_NOTE = re.compile(r"寄港(?:いたし|致し|し)ません")

WEEKDAYS = "月火水木金土日"  # date.weekday() の順


def nearest_date(month: int, day: int, today: date) -> date | None:
    """月日 → 今日にいちばん近い日付になる年の日付。存在しない日付は None。"""
    candidates = []
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            candidates.append(date(year, month, day))
        except ValueError:
            continue
    if not candidates:
        return None
    return min(candidates, key=lambda d: abs((d - today).days))


def parse_search_datetime(text: str) -> datetime | None:
    """「2026年10月4日 05:50」→ datetime。「－」などは None。"""
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{2})", text)
    if not m:
        return None
    try:
        return datetime(*(int(g) for g in m.groups()))
    except ValueError:
        return None


def iso_or_none(v: datetime | None) -> str | None:
    return v.isoformat() if v else None
