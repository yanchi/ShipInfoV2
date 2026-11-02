# Quickstart: スクレイパーを振る舞いを変えずに整理する

## 1. 「前」を取る（research R4）

「前」は**基点のコミット**（このブランチが master から分かれたところ）のコードで、コンテナの `/tmp/base` に展開して取る。作業中のコードに関係なく、いつでも取り直せる。

テストは `date.today()` から日付を作るので、**「前」と「後」は同じ日に取る**（`compare_snapshots.py` は日が違うと止まる）。日をまたいだら、その日の最初の比較の前にここをやり直す。コンテナを作り直して `/tmp` が消えたときも同じ。

```bash
make up
for f in snapshot_plugin.py compare_snapshots.py log_events.py; do
  docker compose cp specs/17-scraper-refactor/$f scraper:/tmp/
done
docker compose exec -T scraper sh -c 'rm -rf /tmp/base && mkdir -p /tmp/base'
git archive "$(git merge-base master HEAD)" scraper | docker compose exec -T scraper tar -x -C /tmp/base
docker compose exec -T scraper sh -c '
  cd /tmp/base/scraper
  for n in 1 2; do
    rm -f /tmp/before$n.jsonl
    PYTHONHASHSEED=0 PYTHONPATH=/tmp SNAPSHOT_OUT=/tmp/before$n.jsonl python -m pytest tests/ -q -p snapshot_plugin
  done
  wc -l < /tmp/before1.jsonl                                   # 336
  python /tmp/log_events.py scraper > /tmp/events_before.txt
  wc -l < /tmp/events_before.txt'                              # 53（ログの出来事の種類。FR-007）
```

`/tmp/base/scraper` で流すと、`scraper` パッケージはそこから読まれる（`/app` のものではない）。

## 2. 区切りごとに：テストと、返したもの・DB の行を比べる

US1・US2 の各コミットの前に毎回やる（spec FR-010：どこで止めても通る）。

```bash
make test-scraper        # 336 passed
make lint-scraper
make check-schema
docker compose exec -T scraper sh -c '
  rm -f /tmp/after.jsonl
  PYTHONHASHSEED=0 PYTHONPATH=/tmp SNAPSHOT_OUT=/tmp/after.jsonl python -m pytest tests/ -q -p snapshot_plugin
  python /tmp/compare_snapshots.py /tmp/before1.jsonl /tmp/before2.jsonl /tmp/after.jsonl
  python /tmp/log_events.py scraper | diff /tmp/events_before.txt - && echo events-same'
# → tests=336 diffs=0
# → events-same
```

- 終了コード 2（テストの集合・取った日が揃わない）なら、比べていない。1 をやり直してから流す
- `diffs` が 0 でなければ、出た（テスト・表・行）を見て、整理で振る舞いが変わったところを戻す（直すのではなく戻す。FR-008）

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
