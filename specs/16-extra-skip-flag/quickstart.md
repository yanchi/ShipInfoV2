# Quickstart: 臨時便の抜港をスクレイパーが行のフラグで持つ

## ローカル

```bash
make up
make migrate            # skips_ports_after を足す
make check-schema       # スクレイパーのモデルの列が DB にあるか
make test-scraper
make test-php
make phpstan && make cs-php && make lint-php && make lint-scraper
```

## 確かめること

1. `make scraper-run` のあと、臨時便がある日は臨時便の行に `skips_ports_after` が入る

   ```sql
   SELECT p.name, d.departure_date, d.ship_name, d.status, d.skips_ports_after
   FROM departure_statuses d JOIN ports p ON p.id = d.port_id
   WHERE d.status = 'extra' ORDER BY d.scheduled_departure_at;
   ```

2. 臨時便でない行の `scraped_at` が、最初のスクレイプで一斉に進んでいない（SC-004）
3. トップの会社カードの臨時便の1行：今日の臨時便の行のどれかが 1 なら「・抜港あり」

## 本番

master に入ると CI がデプロイし、コンテナ起動時にマイグレーションが流れる（[deploy/README.md](../../deploy/README.md)）。既存行は 0 のまま始まり、スクレイパーの次の定期実行で書き直される。手作業は要らない。入れた日に出港済みの臨時便の行は 0 のまま（spec Edge Cases）。
