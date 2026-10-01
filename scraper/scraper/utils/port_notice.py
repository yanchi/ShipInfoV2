"""運航状況テキストから港別情報（条件付寄港・抜港・港変更）を抜き出す（research R4）。

マルエーの過去の異常時ページは公開されておらず実例が無いので、保守的に作っている。
誤判定より取りこぼしを選ぶ（拾えなければ船ステータスで表示する）。

- 対象は鹿児島航路ページの抜粋と、船別詳細ページの h4 の後〜定型の注意書き（「台風の影響や」の段落）の手前
- 文（「。」と改行）ごとに見る。仮定・案内の文（「場合」「ことがあります」「可能性」「問い合わせ」）は除外
- 抜港 → skip、港変更・寄港地変更・「A港からB港へ／に」→ change（B が変更先）、条件付 → conditional
- 1つの港に複数あれば skip > change > conditional
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from scraper.utils.ports import PortResolver

BOILERPLATE_MARKER = "台風の影響や"
_HYPOTHETICAL = ("場合", "ことがあります", "可能性", "問い合わせ")
_CHANGE_ROUTE = re.compile(
    r"([^\s、。・,，:：]+?港)から([^\s、。・,，:：]+?港)(?:へ|に)"
)
_PRIORITY = {"skip": 3, "change": 2, "conditional": 1}


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
    kinds = []
    if "抜港" in text:
        kinds.append("skip")
    if "港変更" in text or "寄港地変更" in text or _CHANGE_ROUTE.search(text):
        kinds.append("change")
    if "条件付" in text:
        kinds.append("conditional")
    return kinds


def _sentence_notices(sentence: str, resolver: PortResolver) -> list[PortNotice]:
    kinds = _kinds(sentence)
    if not kinds:
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

    if len(kinds) == 1:
        clauses = [(sentence, kinds[0])]
    else:
        # 「与論港は抜港、和泊港は条件付寄港」のように種類が混ざる文は読点で分けて、
        # 種類の無い節の港は次の種類のある節にまとめる
        clauses = []
        pending = ""
        for clause in re.split(r"[、，,]", sentence):
            clause_kinds = _kinds(clause)
            if len(clause_kinds) == 1:
                clauses.append((pending + clause, clause_kinds[0]))
                pending = ""
            elif not clause_kinds:
                pending += clause + "、"
            # 1つの節に複数の種類 → 判断できないので使わない

    notices = []
    for clause, kind in clauses:
        for port in resolver.find_all(clause):
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
