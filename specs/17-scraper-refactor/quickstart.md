# Quickstart: スクレイパーを振る舞いを変えずに整理する

## 1. 整理の前に：DB の行を2回とっておく（research R4）

**コードに触る前に**やる。`/tmp` はコンテナの中（`make up` で立てた scraper）。

```bash
make up
docker compose cp specs/17-scraper-refactor/snapshot_plugin.py scraper:/tmp/
docker compose cp specs/17-scraper-refactor/compare_snapshots.py scraper:/tmp/
docker compose exec -T scraper sh -c '
  rm -f /tmp/before1.jsonl /tmp/before2.jsonl
  PYTHONHASHSEED=0 PYTHONPATH=/tmp SNAPSHOT_OUT=/tmp/before1.jsonl python -m pytest tests/ -q -p snapshot_plugin
  PYTHONHASHSEED=0 PYTHONPATH=/tmp SNAPSHOT_OUT=/tmp/before2.jsonl python -m pytest tests/ -q -p snapshot_plugin
  wc -l /tmp/before1.jsonl'   # 270
```

コンテナを作り直すと `/tmp` は消える。消したら master のコードに戻して取り直す（`git stash` か worktree）。

## 2. 区切りごとに：テストと DB の行を比べる

US1・US2 の各コミットの前に毎回やる（spec FR-010：どこで止めても通る）。

```bash
make test-scraper        # 336 passed
make lint-scraper
make check-schema
docker compose exec -T scraper sh -c '
  rm -f /tmp/after.jsonl
  PYTHONHASHSEED=0 PYTHONPATH=/tmp SNAPSHOT_OUT=/tmp/after.jsonl python -m pytest tests/ -q -p snapshot_plugin
  python /tmp/compare_snapshots.py /tmp/before1.jsonl /tmp/before2.jsonl /tmp/after.jsonl'
# → tests=270 masked_cells=95 diffs=0
```

`diffs` が 0 でなければ、出た (テスト, 表, 行, 列) を見て、整理で振る舞いが変わったところを戻す（直すのではなく戻す。FR-008）。

## 3. 終わったら：大きさを確かめる（SC-003・SC-004）

```bash
wc -l scraper/scraper/scrapers/marue_ferry/*.py      # どれも 600 以下
grep -rn "def _load_routes\|def _load_stops" scraper/scraper/scrapers   # base.py だけ
```

## 本番

コードの置き場所が変わるだけ。DB・設定・cron に手作業は要らない。master に入ると CI がイメージを作り直して入れ替える（[deploy/README.md](../../deploy/README.md)）。

入れ替えたあとの最初の定期スクレイプで、両社の `scraper_logs` が成功で、公式ページが変わっていない会社の `departure_statuses.scraped_at` が一斉に進んでいないことを見る（SC-005）。

```sql
SELECT c.name, l.status, l.records_created, l.records_updated, l.started_at
FROM scraper_logs l JOIN ferry_companies c ON c.id = l.ferry_company_id
ORDER BY l.started_at DESC LIMIT 4;
```
