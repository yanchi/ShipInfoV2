# Quickstart: マルエーフェリーの臨時便を港別ステータスに出す

## テスト

```bash
make test-scraper   # pytest（2026-10-26 の波之上の詳細ページを fixture にしたテストを含む）
make lint-scraper
make test-php       # Enum・PortBoardEntry・PortBoardDay・トップ・通知
make phpstan
make cs-php
make lint-php
```

fixture は既存の `scraper/tests/fixtures/marue/ship_detail_naminoue_20261026.html`（`samples/` と同じもの）。

## ローカルで動かす

```bash
make up
make scraper-run
```

公式の詳細ページに臨時便が出ている日なら:

- `/ports`：臨時便の港・日付に「◆ 臨時便」の行。寄港しない港には出ない
- トップ：会社カードの航路の下に「◆ 臨時便 〇〇 HH:MM発」、「欠航・条件付などの便」にも臨時便
- 凡例に「臨時便」

臨時便が出ていない日は、テストの fixture で確かめる（SC-001・SC-002・SC-007）。

通知メールの文面（送らない）:

```bash
make notify-dry-run
```

## 本番で確かめる（デプロイ後）

鍵と接続先は deploy/README.md と同じ。

```bash
ssh -i ~/.ssh/shipinfo-deploy rocky@ship.isl-mentor.com
```

臨時便の行（日付は確かめる日に合わせる）:

```bash
docker exec shipinfo-v2-mysql-1 sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" mysql -u"$MYSQL_USER" "$MYSQL_DATABASE" -e "
SELECT d.departure_date, r.origin_port, p.name, d.ship_name, d.status, d.scheduled_departure_at, d.scheduled_arrival_at, d.source_url
FROM departure_statuses d JOIN routes r ON r.id = d.route_id JOIN ports p ON p.id = d.port_id
JOIN ferry_companies c ON c.id = r.ferry_company_id
WHERE c.scraper_class = \"MarueFerry\" AND d.source_url <> \"https://www.aline-ferry.com/search/result.php\"
  AND d.departure_date >= CURDATE()
ORDER BY d.departure_date, d.scheduled_departure_at"'
```

公式の船の詳細ページ（「欠航と臨時便」など）の【臨時便】と見比べる。

取りやめで消した臨時便の行（`extra_voyage_rows_deleted`：船・件数）と、読めなかった臨時便・便検索とぶつかった臨時便・終点の時刻が変わった臨時便:

```bash
docker logs --since 3h shipinfo-v2-scraper-1 2>&1 | grep -E "extra_voyage_rows_deleted|extra_voyage_unreadable|extra_voyage_key_conflict|extra_voyage_arrival_changed"
```

## ロールバック

前のイメージに戻す前に、`extra` の行を消す（残すと PHP の Enum が読めず、/ports・トップ・会社ページ・通知が失敗する。research R10）:

```bash
docker exec shipinfo-v2-mysql-1 sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" mysql -u"$MYSQL_USER" "$MYSQL_DATABASE" -e "DELETE FROM departure_statuses WHERE status = \"extra\""'
```

そのあとで deploy/README.md の手順でイメージを戻す。スクレイパーも戻るので、`extra` の行はもう作られない。

## 警告への対応

`extra_voyage_unreadable` が出たら、公式の書き方が R1 と違う。保存して `samples/` に足し、読み方を直す。
