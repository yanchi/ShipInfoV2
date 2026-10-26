# Quickstart: 先の便にも公式の便ごとの状態を出す

## テスト

```bash
make test-scraper   # pytest（2026-10-26 の保存ページを fixture にしたテストを含む）
make lint-scraper
```

fixture は `samples/` のコピー（`scraper/tests/fixtures/marue/kagoshima_20261026.html` など）。

## ローカルで動かす

```bash
make up
make scraper-run
```

港別ページ（`/ports`）で、公式の抜粋に便の行がある先の便が、その状態（欠航・条件付など）で出ること。抜粋に行が無い先の便は「運航予定」のまま。

## 本番で確かめる（デプロイ後）

鍵と接続先は deploy/README.md と同じ。

```bash
ssh -i ~/.ssh/shipinfo-deploy rocky@ship.isl-mentor.com
```

「臨時便運航」の警告が出なくなったこと（SC-002）:

```bash
docker logs --since 1h shipinfo-v2-scraper-1 2>&1 | grep -E "unknown_status_text|unknown_voyage_status"
```

先の便の行（SC-001。日付は確かめる日に合わせる）:

```bash
docker exec shipinfo-v2-mysql-1 sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" mysql -u"$MYSQL_USER" "$MYSQL_DATABASE" -e "
SELECT d.departure_date, r.origin_port, p.name, d.ship_name, d.status, d.checked_at
FROM departure_statuses d JOIN routes r ON r.id = d.route_id JOIN ports p ON p.id = d.port_id
JOIN ferry_companies c ON c.id = r.ferry_company_id
WHERE c.scraper_class = \"MarueFerry\" AND d.departure_date BETWEEN CURDATE() AND CURDATE() + INTERVAL 3 DAY
ORDER BY d.departure_date, r.id, d.scheduled_departure_at"'
```

公式の鹿児島航路ページ（https://www.aline-ferry.com/kagoshima/）の抜粋と見比べて、行のある便がその状態になっていること。
