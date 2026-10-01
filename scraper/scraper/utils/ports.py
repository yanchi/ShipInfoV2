"""港名の正規化（research R5）。

各社のページの港の表記（「鹿児島新港」「名瀬港」など）を ports テーブルの港に直す。
別名は長いものから順にマッチさせる（「鹿児島新港」を「鹿児島」より先に）。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from scraper.db.models import Port


class PortResolver:
    def __init__(self, ports: list[Port]) -> None:
        self._ports = list(ports)
        aliases: list[tuple[str, Port]] = []
        for port in self._ports:
            names = {port.name, *(port.aliases or [])}
            aliases.extend((a, port) for a in names if a)
        # 長い別名から試す
        self._aliases = sorted(aliases, key=lambda x: len(x[0]), reverse=True)

    @classmethod
    def from_session(cls, session: Session) -> "PortResolver":
        return cls(list(session.execute(select(Port)).scalars().all()))

    @property
    def ports(self) -> list[Port]:
        return self._ports

    def resolve(self, text: str | None) -> Port | None:
        """文字列に含まれる港を1つ返す（一番長い別名でマッチしたもの）。無ければ None。"""
        if not text:
            return None
        for alias, port in self._aliases:
            if alias in text:
                return port
        return None

    def find_all(self, text: str | None) -> list[Port]:
        """文中に出てくる港を、重複なしで出現順に返す。

        長い別名から順に文中の位置を確保していくので、「鹿児島新港」の中の「鹿児島」を
        二重に数えたりはしない。
        """
        if not text:
            return []
        taken = [False] * len(text)
        hits: list[tuple[int, Port]] = []
        for alias, port in self._aliases:
            start = 0
            while True:
                idx = text.find(alias, start)
                if idx < 0:
                    break
                end = idx + len(alias)
                if not any(taken[idx:end]):
                    for i in range(idx, end):
                        taken[i] = True
                    hits.append((idx, port))
                start = idx + 1
        hits.sort(key=lambda x: x[0])
        result: list[Port] = []
        seen: set[int] = set()
        for _, port in hits:
            if port.id not in seen:
                seen.add(port.id)
                result.append(port)
        return result
