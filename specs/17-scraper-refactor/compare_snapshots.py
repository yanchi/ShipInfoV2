"""snapshot_plugin.py の出力を比べる（17-scraper-refactor の FR-001・SC-002）。

    python compare_snapshots.py before1.jsonl before2.jsonl after.jsonl

before1・before2 は整理の前のコードで2回流した結果、after は整理の後。

- 3つのテストの集合と、取った日（run_date）が全部同じでなければ、比べずに終了コード 2 で止める
  （テストは date.today() から日付を作るので、日が違うと正しい整理でも違いが出る）
- テーブルごとに、before1 と before2 で値の集まりが違う列（datetime.now() から作る時刻と、それで決まる
  content_hash など）を落とし、残りの列で行を多重集合として比べる。行の並び順・位置には頼らない
- 列を落としても before1 と before2 が合わないテーブル、読めなかったテーブル（error）は、
  確かめられないので違いに数える
- after が before1 と違えば、違いを出して終了コード 1 で終わる
"""

import json
import sys
from collections import Counter


def load(path: str) -> dict[str, dict]:
    records: dict[str, dict] = {}
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                sys.exit(f"{path}:{lineno}: JSON として読めない（{e.msg}）。取り直す")
            if rec["test"] in records:
                sys.exit(
                    f"{path}:{lineno}: {rec['test']} が2回ある。出力先を消してから取り直す"
                )
            records[rec["test"]] = rec
    return records


def rows_of(tables: dict, table: str) -> list[dict] | str:
    return tables.get(table, "missing")


def unstable_columns(rows1: list[dict], rows2: list[dict]) -> set[str]:
    cols = {c for r in rows1 + rows2 for c in r}
    return {
        c
        for c in cols
        if Counter(r.get(c) for r in rows1) != Counter(r.get(c) for r in rows2)
    }


def project(rows: list[dict], drop: set[str]) -> Counter:
    return Counter(
        json.dumps(
            {k: v for k, v in r.items() if k not in drop},
            sort_keys=True,
            ensure_ascii=False,
        )
        for r in rows
    )


def main(before1: str, before2: str, after: str) -> int:
    b1, b2, a = load(before1), load(before2), load(after)

    names = {before1: set(b1), before2: set(b2), after: set(a)}
    if len({frozenset(s) for s in names.values()}) != 1:
        everyone = set.intersection(*names.values())
        for path, tests in names.items():
            extra = sorted(tests - everyone)
            if extra or len(tests) != len(everyone):
                print(f"{path}: {len(tests)} テスト（ほかに無いもの {extra[:5]}）")
        print(
            "テストの集合が揃っていない。pytest が途中で止まっていないか見て、取り直す"
        )
        return 2
    dates = {
        path: {r["run_date"] for r in recs.values()}
        for path, recs in ((before1, b1), (before2, b2), (after, a))
    }
    if len(set().union(*dates.values())) != 1:
        print(f"取った日が違う: {dates}")
        print("quickstart の 1 で、基点のコミットから before を今日取り直す")
        return 2

    problems: list[str] = []
    masked: Counter = Counter()
    for test in sorted(b1):
        t1, t2, ta = b1[test]["tables"], b2[test]["tables"], a[test]["tables"]
        for table in sorted(set(t1) | set(t2) | set(ta)):
            r1, r2, ra = rows_of(t1, table), rows_of(t2, table), rows_of(ta, table)
            if any(isinstance(r, str) for r in (r1, r2, ra)):
                if not all(isinstance(r, list) for r in (r1, r2, ra)):
                    problems.append(
                        f"{test} {table}: 読めない（前 {r1!r:.40} / 後 {ra!r:.40}）"
                    )
                continue
            drop = unstable_columns(r1, r2)
            masked.update(f"{table}.{c}" for c in drop)
            p1, p2, pa = project(r1, drop), project(r2, drop), project(ra, drop)
            if p1 != p2:
                problems.append(
                    f"{test} {table}: 前の2回が列を落としても合わない（確かめられない）"
                )
                continue
            if p1 != pa:
                for row in sorted((p1 - pa).elements()):
                    problems.append(f"{test} {table}: 前だけ {row}")
                for row in sorted((pa - p1).elements()):
                    problems.append(f"{test} {table}: 後だけ {row}")
    print(f"tests={len(b1)} diffs={len(problems)}")
    print(f"masked_columns={dict(sorted(masked.items()))}")
    for p in problems[:50]:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(
            f"使い方: python {sys.argv[0]} before1.jsonl before2.jsonl after.jsonl"
        )
    sys.exit(main(*sys.argv[1:]))
