"""スクレイパーのログの出来事（レベル・名前・呼んでいる数）を並べる（17-scraper-refactor の FR-007）。

    python log_events.py scraper/scrapers > /tmp/events_before.txt

整理の前後で出力を diff する。ファイルをまたいで集計するので、メソッドを別のファイルに移しても同じになる。
"""

import collections
import pathlib
import re
import sys

_CALL = re.compile(r"(?:_log|\blog)\.(\w+)\(\s*\"(\w+)\"")


def main(root: str) -> None:
    counts: collections.Counter[tuple[str, str]] = collections.Counter()
    for path in sorted(pathlib.Path(root).rglob("*.py")):
        counts.update(m.groups() for m in _CALL.finditer(path.read_text()))
    for (level, event), n in sorted(counts.items()):
        print(f"{level} {event} {n}")


if __name__ == "__main__":
    main(sys.argv[1])
