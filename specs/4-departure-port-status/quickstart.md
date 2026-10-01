# Quickstart: 出発港別の運航情報表示

**Feature**: 4-departure-port-status

## セットアップ

```bash
make up                 # TZ=Asia/Tokyo を反映するため scraper コンテナは作り直す
docker compose up -d --force-recreate scraper
make migrate            # ports / port_company_codes / route_stops / departure_statuses、routes.direction
# テスト用 DB（*_test）にも適用する（make test-php の前に必須）
docker compose exec php bin/console doctrine:migrations:migrate --env=test --no-interaction
```

JST になったかの確認:

```bash
docker compose exec scraper python -c "import datetime; print(datetime.datetime.now())"   # ホストの JST と一致すること
```

## 動作確認

```bash
make scraper-run        # 2社を即時実行
```

1. `http://localhost:<port>/ports` を開く
2. 今日〜3日先の日付セクションが並び、各日付に「下り（那覇行き）」「上り（鹿児島行き）」×6港が出ること
3. その日に運航している会社の便だけが出ていて、運航してない会社の「便なし」が混ざってないこと
4. 3日先のマルエーの便が「運航予定」で出ていること
5. 各行の「○時○分時点」が直近の実行時刻（JST）になっていること

DB の確認:

```sql
SELECT r.direction, p.name, d.departure_date, fc.name AS company, d.ship_name, d.status,
       d.scheduled_departure_at, d.checked_at, d.operated_by_company_id
FROM departure_statuses d
JOIN routes r ON r.id = d.route_id
JOIN ferry_companies fc ON fc.id = r.ferry_company_id
JOIN ports p ON p.id = d.port_id
WHERE d.departure_date >= CURDATE()
ORDER BY d.departure_date, r.direction, p.id, fc.id;
```

## テスト

```bash
make test-scraper
make test-php
```

## マルエーの便検索を手で叩く

```bash
curl -s -X POST https://www.aline-ferry.com/search/result.php \
  --data-urlencode "startDate=2026年10月04日" --data "startPort=70&endPort=83"
```

日付は必ず `YYYY年MM月DD日` 形式で送る。ISO 形式だと常に「※下記参照」が返る（research R3）。

## 異常時のページを見つけたら（港別情報のルール改善）

マルエーの過去の運航状況ページは公開されていないので、港別情報の抽出ルール（research R4）は実例なしで作っている。条件付寄港・抜港・港変更が出ている日を見つけたら：

1. 鹿児島航路ページと船別詳細ページの HTML を `scraper/tests/fixtures/marue/` に日付つきで保存する
2. その fixture でテストを追加して、`scraper/scraper/utils/port_notice.py` のルールを直す
3. warning ログの `port_notice_unmatched` を確認して、拾えてない言い回しを洗い出す
