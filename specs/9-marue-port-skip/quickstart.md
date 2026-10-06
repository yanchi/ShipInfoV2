# Quickstart: 抜港を「抜港」と表示する

## 自動テストで確かめる

```bash
make test-scraper   # 保存版（2026-10-06）で 和泊・与論＝抜港、亀徳＝条件付・遅延、欠航0件（SC-001）
make test-php       # バッジ・異常の要約・出港済み・通知メールの「抜港」
make lint-scraper && make cs-php && make phpstan && make lint-php
```

主なテスト（tasks.md で作る）:

| 確かめること | テスト |
|---|---|
| 「寄港いたしません」などで skip になる・仮定の文は除く | `scraper/tests/test_port_notice.py` |
| 括弧書きのある列挙（和泊港(沖永良部島)・与論港(与論島)）で2港とも拾う | `scraper/tests/test_port_notice.py` |
| 保存版と「寄港いたしません」だけ版で同じ結果 | `scraper/tests/test_marue_ferry.py` |
| タグの並びを入れ替えても同じ結果 | `scraper/tests/test_marue_ferry.py` |
| 船が欠航なら全港欠航（抜港にならない） | `scraper/tests/test_marue_ferry.py` |
| マリックスの「寄港しません」が抜港 | `scraper/tests/test_marix_line.py`（`downstream_route_change.html`） |
| 航路単位は抜港にならない | 両社のテスト |
| 抜港のバッジ・凡例・出港済みにならない | `app/tests/View/PortBoardEntryTest.php`・`app/tests/Controller/StatusControllerTest.php` |
| 通知メールの港の行が「抜港」 | `app/tests/Service/IrregularStatusMailerTest.php` |

## 画面で見る

```bash
make up
make migrate
```

phpMyAdmin（`make up-tools`）などで、今日〜3日先の `departure_statuses` の1行の `status` を `skipped` にして、

- `/` の「欠航・条件付などの便」に `≫ 抜港` が入る
- `/ports`・`/company/{id}` の該当の行がオレンジで強調され、予定出港時刻を過ぎても「出港済み」にならない
- 「ステータスの見かた」に抜港がある
- 会社カード（航路単位）には抜港が出ない

## 通知メールで見る

```bash
make notify-dry-run   # 上で skipped にした行が「…：抜港」と出る
```

## 本番で確かめる

マルエー・マリックスの告知に抜港・「寄港しません」が出たとき、

1. 公式の告知と、`/ports` の該当の港の行が「抜港」になっているかを見比べる
2. 抜港なのに別のステータスになっていたら、スクレイパーのログの `port_notice_unmatched`（条件付の船で港別情報が読めなかった）と `search_datetime_missing` を見る
3. 新しい言い回しなら `port_notice.py` の skip の正規表現に足して、その文面をテストに加える（spec Assumptions）
