"""snapshot_plugin.py の出力を比べる（17-scraper-refactor の FR-001・SC-002）。

    python compare_snapshots.py before1.jsonl before2.jsonl after.jsonl

before1・before2 は整理の前に2回流した結果。テストの中には datetime.now() から時刻を作るものがあり、
その列（と、それで決まる content_hash）は実行のたびに変わる。2回の前で違った (テスト, 表, 行, 列) は
比べない。それ以外で after が before1 と違えば、違いを出して終了コード 1 で終わる。
"""

import json
import sys


def load(path: str) -> dict[str, dict]:
    with open(path, encoding="utf-8") as f:
        return {(rec := json.loads(line))["test"]: rec["tables"] for line in f}


def cells(tables: dict) -> dict[tuple, str]:
    out: dict[tuple, str] = {}
    for table, rows in tables.items():
        if isinstance(rows, str):
            out[(table, "-", "-")] = rows
            continue
        out[(table, "count", "-")] = str(len(rows))
        for i, row in enumerate(rows):
            for col, value in row.items():
                out[(table, i, col)] = value
    return out


def main(before1: str, before2: str, after: str) -> int:
    b1, b2, a = load(before1), load(before2), load(after)
    problems: list[str] = []
    if set(b1) != set(a):
        problems.append(
            f"テストの集合が違う: 前だけ {sorted(set(b1) - set(a))} 後だけ {sorted(set(a) - set(b1))}"
        )
    masked = 0
    for test in sorted(set(b1) & set(a)):
        c1, c2, ca = cells(b1[test]), cells(b2.get(test, {})), cells(a[test])
        unstable = {k for k in c1 if c2.get(k) != c1[k]}
        masked += len(unstable)
        for key in sorted(set(c1) | set(ca), key=str):
            if key in unstable:
                continue
            if c1.get(key) != ca.get(key):
                problems.append(
                    f"{test} {key}: 前 {c1.get(key)!r} → 後 {ca.get(key)!r}"
                )
    print(f"tests={len(b1)} masked_cells={masked} diffs={len(problems)}")
    for p in problems[:50]:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
