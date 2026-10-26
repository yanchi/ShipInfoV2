# Quickstart: マリックスラインの臨時便を港別ステータスに出す

## テスト

```bash
make test-scraper   # pytest（2026-08〜09 の臨時便・定期便の詳細ページを fixture にしたテストを含む）
make lint-scraper
make test-php       # StatusController（臨時便しか無い日のバッジ）
make phpstan
make cs-php
make lint-php
```

fixture は `samples/` の詳細ページを `scraper/tests/fixtures/marix/` に置いたもの。一覧の HTML は、今の `list.html` の形で臨時便の便を並べたものをテストの中で作る（実物の一覧は未確認。R1）。

| fixture | 中身 |
|---|---|
| `extra_down_20260906.html`（service6727） | 9/6 下り 臨時便・航行経路変更（クロス、鹿児島 09:00 → 那覇） |
| `down_route_change_20260906.html`（downstream20260906） | 9/6 下り 定期便（プラス、条件付運航） |
| `extra_up_20260907.html`（service6731） | 9/7 上り 臨時便運航（クロス、那覇 07:00 → 名瀬 21:20 → 鹿児島） |
| `up_cancel_20260907.html`（upstream20260907） | 9/7 上り 定期便（クロス、欠航） |
| `extra_up_naze_20260927.html`（service6819） | 9/27 上り 臨時便（クロス、名瀬 05:50 → 鹿児島。寄らない港に 08/25） |
| `extra_down_20260827.html`（service6664） | 8/27 下り 臨時便（クロス、鹿児島 10:00 → 那覇） |

## ローカルで動かす

```bash
make up
make scraper-run
```

公式の一覧に臨時便が出ている日なら:

- `/ports`：臨時便が寄る港・日付に「◆ 臨時便」の行。寄らない港には臨時便の行が無い
- 同じ船の定期便が欠航なら、臨時便が寄る港は「◆ 臨時便」、寄らない港は「✗ 欠航」
- トップ：会社カードの航路のバッジは定期便の状態。下に「◆ 臨時便 〇〇 HH:MM発」
- スクレイパーのログに `unknown_status_class`・`detail_status_unknown` が出ない

一覧に臨時便が出たら、一覧の HTML を保存して R1 の推測（一覧の便のクラスに `temporary`）を確かめる:

```bash
curl -s https://marixline.com/service/ > specs/13-marix-extra-voyages/samples/list_with_extra.html
grep -o 'status_single_cover[^"]*' specs/13-marix-extra-voyages/samples/list_with_extra.html | sort | uniq -c
```

## 本番で確かめる（デプロイ後）

鍵と接続先は deploy/README.md と同じ。臨時便が出ている日に:

```sql
SELECT departure_date, port_id, ship_name, status, scheduled_departure_at, source_url
FROM departure_statuses
WHERE route_id IN (SELECT id FROM routes WHERE ferry_company_id = (SELECT id FROM ferry_companies WHERE scraper_class = 'MarixLine'))
  AND departure_date >= CURDATE()
ORDER BY departure_date, route_id, scheduled_departure_at;
```

- 臨時便の行は `status = 'extra'`、`source_url` が臨時便の詳細ページ
- 同じ航路・港・出港日に、船名ありの行と船名なしの行が並んでいない
