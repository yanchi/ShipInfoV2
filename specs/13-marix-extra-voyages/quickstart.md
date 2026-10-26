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
- 同じ航路・港・出港日に船名ありの行と船名なしの行が並ぶのは、定期便の詳細ページが取れなかった回だけ（FR-015）。次の回（詳細ページが取れた回）には船名なしの行が消えている

スクレイパーのログ（`scraper_logs` の横の標準出力）に出る警告:

| イベント名 | 意味 | 見るところ |
|---|---|---|
| `extra_voyage_detail_missing`（url・route_id） | 臨時便の詳細ページが取れず、行を作らなかった。前の回の行はそのまま | 次の回に取れれば直る。続くなら公式の詳細ページを確かめる |
| `extra_voyage_conflict`（key・regular_url・extra_url） | 同じキーに、走る定期便と臨時便が来た。定期便の行を残した（詳細に「（臨時便 HH:MM発あり）」）。キーごとに1件 | 公式の記録に前例が無い。実際に両方走るのか確かめる |
| `voyage_kind_unknown`（url） | 一覧のクラスが読めず、詳細ページも取れない便。航路単位を書かなかった | 一覧の HTML が変わっていないか。詳細ページが取れれば次の回で直る |
| `departure_duplicate_key` | Base が同じキーの2本目を捨てた。臨時便と定期便の組では出ない | 出たら `_resolve_extra_conflicts()` を通っていない |

## SC-005 を確かめるテスト

9/7 の一覧（定期便の欠航＋臨時便）を、DB・画面・通知に通した形。

| 見るところ | テスト |
|---|---|
| DB（航路単位が `cancelled`、那覇・名瀬のクロスが `extra`） | `scraper/tests/test_marix_line.py::test_run_writes_route_level_and_extra_rows_for_0907` |
| トップ（航路が欠航・臨時便あり →「✗ 欠航」と「◆ 臨時便 〇〇 HH:MM発」） | `StatusControllerTest::testIndexCardShowsExtraDepartureUnderRouteBadge`（12）・`testIndexCardOriginExtraKeepsCancelledBadge`（13） |
| 通知メール（欠航の航路に Extra の港 → 状況は「欠航」、港は「臨時便」） | `IrregularServiceCollectorTest::testStatusTextForExtraPorts`（「欠航は今までどおり」）・`IrregularStatusMailerTest::testExtraPortsAreLabeledExtra`（12） |
