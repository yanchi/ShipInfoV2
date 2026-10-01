"""運航状況テキストから港別情報（条件付寄港・抜港・港変更）を抜き出す（research R4）。

マルエーの過去の異常時ページは公開されておらず実例が無いので、保守的に作っている。
誤判定より取りこぼしを選ぶ（拾えなければ船ステータスで表示する）。

- 対象は鹿児島航路ページの抜粋と、船別詳細ページの h4 の後〜定型の注意書き（「台風の影響や」の段落）の手前
- 文（「。」と改行）ごとに見る。仮定・案内の文（「場合」「ことがあります」「可能性」「問い合わせ」）は除外
- 抜港 → skip、港変更・寄港地変更・「A港からB港へ／に」→ change（B が変更先）、条件付 → conditional
- 対象の港は読点で区切った節ごとに決める
  - キーワードのある節：キーワードの直前の港と、それに「・」「と」でつながる港
    （「与論港は抜港して那覇港へ」なら与論だけ、「鹿児島新港を出港後与論港は抜港」も与論だけ）。
    前に港が無ければ直後から同じようにたどる（「条件付寄港地: 和泊港」）
  - 港名だけの節（「和泊港、与論港は条件付寄港」の「和泊港」）：隣のキーワードの節にまとめる
  - それ以外の節（「鹿児島新港を出港し」など）の港は対象にしない
  - 「鹿児島新港発の便は」「鹿児島航路は」のように、すぐ後ろに発・着・向け・行き・航路が付く港は
    便・航路の説明なので対象にしない
- 1つの港に複数あれば skip > change > conditional
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from scraper.db.models import Port
from scraper.utils.ports import PortResolver

BOILERPLATE_MARKER = "台風の影響や"
_HYPOTHETICAL = ("場合", "ことがあります", "可能性", "問い合わせ")
# 港名は漢字・カタカナだけで書かれる。ひらがなを含めると「鹿児島新港を出港後亀徳港から」のように
# 前の文まで巻き込んで、変更元の港を取り違えるため
_CHANGE_ROUTE = re.compile(r"([一-龥々ァ-ヶー]+?港)から([一-龥々ァ-ヶー]+?港)(?:へ|に)")
_PRIORITY = {"skip": 3, "change": 2, "conditional": 1}
# 港名の直後にこれが付いていたら、便・航路の説明（「鹿児島新港発の便」「鹿児島航路」）
_VOYAGE_SUFFIXES = ("発", "着", "向け", "行き", "行", "航路")
# 港名を取り除いたあとにこれしか残らない節は「港名だけの節」
_PORT_LIST_REST = re.compile(r"^[\s・と及び]*$")
# 並んだ港名のあいだにこれしか無ければ、同じ扱いの港の列挙（「和泊港・与論港」）
_LIST_GAP = re.compile(r"^[\s・と及び]*$")


@dataclass(frozen=True)
class PortNotice:
    port_id: int
    kind: str  # "conditional" / "skip" / "change"
    change_to: str | None
    sentence: str


def extract_notice_text(excerpt: str | None, detail_html: str | None) -> str:
    """抜粋と、詳細ページの本文（h4 の後〜定型の注意書きの手前）をつなげる。区切りが無ければ抜粋だけ。"""
    parts = [excerpt] if excerpt else []
    if detail_html:
        body = _detail_body(detail_html)
        if body:
            parts.append(body)
    return "\n".join(parts)


def _detail_body(detail_html: str) -> str | None:
    soup = BeautifulSoup(detail_html, "lxml")
    archive = soup.select_one("div.status-archive")
    h4 = archive.find("h4") if archive else None
    if h4 is None:
        return None
    texts: list[str] = []
    for el in h4.find_all_next(["p", "li"]):
        if archive not in el.parents:
            break
        text = el.get_text(" ", strip=True)
        if BOILERPLATE_MARKER in text:
            return "\n".join(texts)
        if text:
            texts.append(text)
    return None  # 定型文の区切りが見つからない → 本文は使わない


def extract_port_notices(text: str, resolver: PortResolver) -> list[PortNotice]:
    found: dict[int, PortNotice] = {}
    for sentence in _sentences(text):
        if any(word in sentence for word in _HYPOTHETICAL):
            continue
        for notice in _sentence_notices(sentence, resolver):
            cur = found.get(notice.port_id)
            if cur is None or _PRIORITY[notice.kind] > _PRIORITY[cur.kind]:
                found[notice.port_id] = notice
    return list(found.values())


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[。\n]", text or "") if s.strip()]


def _kinds(text: str) -> list[str]:
    return [
        kind
        for kind in ("skip", "change", "conditional")
        if _keyword_pos(text, kind) is not None
    ]


def _keyword_pos(text: str, kind: str) -> int | None:
    """節の中でその種類のキーワードが出てくる位置（無ければ None）。"""
    if kind == "skip":
        positions = [text.find("抜港")]
    elif kind == "change":
        positions = [text.find("港変更"), text.find("寄港地変更")]
        m = _CHANGE_ROUTE.search(text)
        if m:
            positions.append(m.end(1))  # 「から」の位置。変更元の港がその直前に来る
    else:
        positions = [text.find("条件付")]
    positions = [p for p in positions if p >= 0]
    return min(positions) if positions else None


def _sentence_notices(sentence: str, resolver: PortResolver) -> list[PortNotice]:
    if not _kinds(sentence):
        return []

    # 「A港からB港へ」の B は変更先なので、港別情報の対象から外す
    change_to: dict[int, str] = {}
    destinations: set[int] = set()
    for m in _CHANGE_ROUTE.finditer(sentence):
        src, dst = resolver.resolve(m.group(1)), resolver.resolve(m.group(2))
        if dst is not None:
            destinations.add(dst.id)
        if src is not None:
            change_to[src.id] = m.group(2)

    # 節ごとに (種類, 対象の港) を作る
    groups: list[tuple[str, list[Port]]] = []
    pending: list[Port] = []  # キーワードの節より前にある「港名だけの節」の港
    last: tuple[str, list[Port]] | None = (
        None  # 直前のキーワードの節（後ろに続く港名だけの節をまとめる）
    )
    for clause in re.split(r"[、，,]", sentence):
        kinds = _kinds(clause)
        hits = _port_hits(clause, resolver)
        if len(kinds) == 1:
            targets = _keyword_ports(clause, hits, _keyword_pos(clause, kinds[0]))
            last = (kinds[0], pending + targets)
            groups.append(last)
            pending = []
        elif not kinds and hits and _is_port_list(clause, resolver):
            if last is not None:
                last[1].extend(port for _, _, port in hits)
            else:
                pending.extend(port for _, _, port in hits)
        else:
            # 1つの節に複数の種類（判断できない）、または港名以外の文がある節 → まとめを切る
            pending = []
            last = None

    notices = []
    for kind, ports in groups:
        for port in ports:
            if port.id in destinations:
                continue
            notices.append(
                PortNotice(
                    port_id=port.id,
                    kind=kind,
                    change_to=change_to.get(port.id) if kind == "change" else None,
                    sentence=sentence,
                )
            )
    return notices


def _port_hits(clause: str, resolver: PortResolver) -> list[tuple[int, int, Port]]:
    """節の中の港を (開始, 終了, 港) で返す。「〇〇港発」「〇〇航路」など便・航路の説明に出てくる港は除く。"""
    return [
        (start, end, port)
        for start, end, port in resolver.find_occurrences(clause)
        if not clause.startswith(_VOYAGE_SUFFIXES, end)
    ]


def _keyword_ports(
    clause: str, hits: list[tuple[int, int, Port]], pos: int
) -> list[Port]:
    """キーワードの対象の港：キーワードの直前の港と、それに「・」「と」でつながる港。

    「鹿児島新港を出港後与論港は抜港」の鹿児島のように、あいだに別の言葉が入る港は含めない。
    キーワードより前に港が無ければ、直後の港から同じようにたどる（「条件付寄港地: 和泊港・与論港」）。
    """
    before = [h for h in hits if h[1] <= pos]
    if before:
        chain = [before[-1]]
        for h in reversed(before[:-1]):
            if not _LIST_GAP.match(clause[h[1] : chain[-1][0]]):
                break
            chain.append(h)
        return [port for _, _, port in reversed(chain)]
    after = [h for h in hits if h[0] >= pos]
    if not after:
        return []
    chain = [after[0]]
    for h in after[1:]:
        if not _LIST_GAP.match(clause[chain[-1][1] : h[0]]):
            break
        chain.append(h)
    return [port for _, _, port in chain]


def _is_port_list(clause: str, resolver: PortResolver) -> bool:
    """港名だけの節か（「和泊港・与論港」など）。"""
    rest = clause
    for start, end, _ in sorted(resolver.find_occurrences(clause), reverse=True):
        rest = rest[:start] + rest[end:]
    return bool(_PORT_LIST_REST.match(rest))
