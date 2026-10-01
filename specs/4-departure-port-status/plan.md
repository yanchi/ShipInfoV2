# Implementation Plan: 出発港別の運航情報表示

**Branch**: `4-departure-port-status` | **Date**: 2026-10-01 | **Spec**: [spec.md](spec.md)

---

## Summary

鹿児島〜那覇航路の運航情報を、2社（マルエーフェリー・マリックスライン）をまとめて「出発港 × 方向（到着港固定）× 出港日」の行で表示する新ページ `/ports` を作る。

- **マリックスライン**: 便別詳細ページから、港ごとのステータスと出入港日時を取る。
- **マルエーフェリー**: 「出発港 × 到着港 × 日付」の便検索で、行ごとの船と出港日時を決める。そこに船ステータスと、運航状況テキストから抜き出した港別情報を重ねる。
- 港別の結果は新しい `departure_statuses` テーブルに入れる。表示側で2社分を合成する。

あわせて、次の既存の不具合を直す。

- スクレイパーが UTC で動いている
- マルエーの便検索の日付形式が間違っていて、常に「便あり」になっている
- 最終確認時刻が取れない

---

## Technical Context

**Language/Version**: Python 3.12 / PHP 8.3
**Primary Dependencies**: requests, BeautifulSoup4 (lxml), SQLAlchemy 2.0 / Symfony 7.4, Doctrine ORM, Twig
**Storage**: MySQL 8.0。新規テーブル4つと `routes.direction` の追加（Doctrine Migration）
**Testing**: pytest（実サイトから保存した HTML fixture で確認）/ PHPUnit（ビルダーの単体テスト、Controller の機能テスト）
**Target Platform**: Docker Compose（scraper / php / nginx / mysql）
**Project Type**: スクレイパー + Web アプリ（MVP、Twig）
**Performance Goals**: マルエーの検索は通常1回あたり24件、6時間ごとに48件（research R8）。`/ports` は DB クエリ1〜2本で組み立てる
**Constraints**:
- `BaseScraper.fetch()` / `parse()` のシグネチャは変えない
- 既存の `/`・`/company/{id}` の表示の構成は変えない
- 日付・時刻はすべて naive な JST で扱う
**Scale/Scope**: 7港・4航路。行は 12 × 4日 × 2社 ＝ 1日あたり最大96行

未解決の NEEDS CLARIFICATION は無い（research.md で全部解決済み）。

---

## Constitution Check

| Gate | Status | 備考 |
|---|---|---|
| I. スクレイパーは `BaseScraper` 継承・会社ごとに独立 | ✅ PASS | 港別の処理は各社のクラスに `parse_departures()` として実装する。共通の upsert と港名の正規化は Base とユーティリティに置く |
| II. Twig + Controller、API なし、スクレイパーは DB に直接書く | ✅ PASS | `/ports` は Controller と Twig。スクレイパーが `departure_statuses` に直接書く |
| III. `raw_html_hash` で重複防止・キーごとの最新状態を保持・ログは `scraper_logs` | ✅ PASS（[#20](https://github.com/yanchi/ShipInfoV2/issues/20) で constitution v2.0.0 に改めた） | `operation_statuses` は今までどおり書く。`departure_statuses` は行ごとの `content_hash` で、変化が無ければ内容を書き換えない。港別の行は「その日の最新状態」で、変更履歴は持たない（constitution v2.0.0 の III どおり）。港別の取得に失敗したときは `scraper_logs.error_message` に記録して、航路単位の記録は成功扱いのまま続ける |
| IV. Docker で完結 | ✅ PASS | TZ は `docker-compose.yml` の環境変数で設定する。マイグレーションは `make migrate` |
| V. フェーズごとにコミット | ✅ PASS | 下の Phase A〜E を tasks.md のグループにして、グループごとにコミットする |
| 技術スタック（変更禁止） | ✅ PASS | 新しいライブラリは入れない |

**Phase 1 設計の後に再チェック**: 違反は無し。III の「港別の行は最新状態だけ」はトレードオフとして上に書いておいた。

---

## Project Structure

### Documentation

```
specs/4-departure-port-status/
├── spec.md
├── research.md
├── data-model.md
├── contracts/http-routes.md
├── quickstart.md
├── plan.md          ← このファイル
└── tasks.md         （/speckit.tasks で生成）
```

### 変更対象

```
docker-compose.yml                                   # scraper に TZ: Asia/Tokyo
docker/mysql/init/01_schema.sql                      # 港別のテーブルはマイグレーションで作る旨のコメントだけ（二重適用を防ぐ）

app/migrations/VersionYYYYMMDDHHMMSS.php             # 新規テーブル + routes.direction + 初期データ
app/src/Entity/Port.php                              # 新規
app/src/Entity/PortCompanyCode.php                   # 新規
app/src/Entity/RouteStop.php                         # 新規
app/src/Entity/DepartureStatus.php                   # 新規
app/src/Entity/Route.php                             # direction, stops を追加
app/src/Enum/RouteDirectionEnum.php                  # 新規（down / up）
app/src/Enum/DepartureDisplayStateEnum.php           # 新規（status / scheduled / no_info / no_service）
app/src/Repository/DepartureStatusRepository.php     # 新規 findForBoard()
app/src/Repository/RouteStopRepository.php           # 新規（方向ごとの寄港順）
app/src/View/PortBoard*.php                          # 新規（ビューモデル）
app/src/Service/PortBoardBuilder.php                 # 新規（2社の合成ルール）
app/src/Controller/StatusController.php              # ports() を追加
app/src/DataFixtures/AppFixtures.php                 # 港・寄港順・港別ステータスのサンプル
app/templates/status/_status_badge.html.twig         # 新規（バッジを共通化）
app/templates/status/ports.html.twig                 # 新規
app/templates/status/index.html.twig                 # バッジをパーシャルにする + 「港別に見る」リンク
app/templates/status/company.html.twig               # バッジをパーシャルにする
app/tests/Service/PortBoardBuilderTest.php           # 新規
app/tests/Controller/StatusControllerTest.php        # /ports のテストを追加
app/tests/Repository/DepartureStatusRepositoryTest.php # 新規

scraper/scraper/db/models.py                         # Port / PortCompanyCode / RouteStop / DepartureStatus、Route.direction
scraper/scraper/config.py                            # MARUE_FAR_SEARCH_INTERVAL_HOURS / MARUE_SEARCH_DELAY_SECONDS
scraper/scraper/scrapers/base.py                     # parse_departures() フック、_upsert_departures()
scraper/scraper/utils/ports.py                       # 新規：港名の正規化（別名マッチ）
scraper/scraper/utils/port_notice.py                 # 新規：運航状況テキストから港別情報を抜き出す
scraper/scraper/scrapers/marix_line.py               # 便別詳細ページの取得と解析
scraper/scraper/scrapers/marue_ferry.py              # 日付形式の修正、方向別の便有無、港別検索、船の対応付け
scraper/tests/fixtures/marix/*.html                  # 新規（実サイトのページを保存）
scraper/tests/fixtures/marue/*.html                  # 新規
scraper/tests/test_ports.py                          # 新規
scraper/tests/test_port_notice.py                    # 新規
scraper/tests/test_base_departures.py                # 新規（upsert のルール）
scraper/tests/test_marix_line.py                     # 港別のテストを追加
scraper/tests/test_marue_ferry.py                    # 日付形式・方向別・港別のテスト、既存のサンプルを直す
```

---

## Phase 0: Research 結果

→ [research.md](research.md)

| # | 決めたこと |
|---|---|
| R1 | マリックスの港別は詳細ページの `div.service > div.single`。年は URL の始発日から補う |
| R2 | マリックスの一覧に何日先まで載るかには依存しない。マルエーの「※下記参照」で補う |
| R3 | マルエーの検索は `YYYY年MM月DD日` 形式で送る。港コードは DB に持つ。日数オフセットは予備用 |
| R4 | 港別情報の抽出では、定型の注意書きと仮定の文を除外する。実例が無いので保守的にする |
| R5 | 港の別名は `ports.aliases` に持たせて、長いものから順にマッチ |
| R6 | `TZ=Asia/Tokyo`。naive な JST で統一 |
| R7 | `content_hash` が同じなら `checked_at` だけ更新 |
| R8 | 今日・明日は毎回、2〜3日先は検索キーごとに6時間たったら検索。検索の間に0.5秒待つ |
| R9 | 船ステータスは「まだ終わってない一番早い便」にだけ当てはめる。出港済みの行は確定させて、`checked_at` も進めない |
| R10 | マルエーの航路単位の記録も、方向ごとに正しい便有無になる |

---

## Phase 1: 設計

→ [data-model.md](data-model.md) / [contracts/http-routes.md](contracts/http-routes.md) / [quickstart.md](quickstart.md)

### スクレイパーの処理の流れ

```
BaseScraper.run()
  html    = fetch()                    # 各社：必要なページを全部取って self に持たせる
  records = parse(html)                # 航路単位（今までどおり）→ _upsert()
  try:
    with session.begin_nested():       # SAVEPOINT。失敗してもここだけ戻す
      deps = parse_departures()        # 港別（デフォルトは []）
      _upsert_departures(deps)         # content_hash / checked_at / 確定・削除のルール
  except: scraper_logs.error_message に記録（航路単位の結果と scraper_logs はコミットされる）
```

`parse_departures()` が返す dict:
`route_id, port_id, departure_date, ship_name, status(None可), status_detail, scheduled_departure_at, scheduled_arrival_at, operated_by_company_id, source_url, freeze_after_departure(bool), replace_scope(tuple|None)`

- `freeze_after_departure`：マルエーは True（FR-020）
- `replace_scope`：マルエーは `(route_id, port_id, departure_date)`。このキーで今回の結果に無い行を消す（data-model の更新ルール5）

### マリックスライン

1. `fetch()`：一覧ページを取る → 各便の `a.status_single[href]` で詳細ページを取る（失敗しても続ける）
2. `parse()`：今までどおり
3. `parse_departures()`：便ごとに
   - 詳細ページあり：`div.single` ごとに港を正規化 → 寄港順にある終点以外の港の行を作る。ステータスは class、日時は「出港」ラベル
   - 詳細ページなし：便のステータスを全出発港に当てはめる。出港日は始発日 + `day_offset`、時刻は空（予備ルート。warning）

### マルエーフェリー

1. `fetch()`：
   - 港別の検索（今日・明日は毎回、2〜3日先は前回から6時間たってたら）
   - 鹿児島航路ページを取る
   - 船別詳細ページを取る
2. `parse()`：鹿児島→那覇、那覇→鹿児島 の当日の検索結果から、方向ごとに便があるかを判定する。会社名が「マルエーフェリー」の行が無ければ `no_service`。便があれば、その船の船ステータスを入れる
3. `parse_departures()`：
   - 検索結果ごとに行を作る
     - 結果0件 → `no_service`
     - 他社運航 → `no_service` + `operated_by` = マリックスライン
     - 船名あり → 便 `(船, 方向, 下船日時)` を特定する
   - 船ごとに、まだ終わってない一番早い便の行には「船ステータス + 港別情報」を入れて、それより後の便は `status=None` にする（research R9）
   - 船名が船ステータスの一覧に無い → `unknown` + warning

### Web（Symfony）

- `DepartureStatusRepository::findForBoard($from, $days)`：期間内の `departure_statuses` を route / port / company と JOIN して、1本のクエリで取る
- `RouteStopRepository`：方向ごとの寄港順（終点を除く）と終点の港
- `PortBoardBuilder::build($stops, $statuses, $today)`：data-model の合成ルール1〜5。DB に依存しない純粋なクラスにして、単体テストで分岐を全部確かめる
- `StatusController::ports()` → `ports.html.twig`

---

## 実装フェーズ（tasks.md のグループのもと）

| Phase | 内容 | 完了条件 |
|---|---|---|
| A. 基盤 | TZ の修正、マイグレーション（テーブル + 初期データ）、Doctrine のエンティティ、SQLAlchemy のモデル、seed / fixtures | `make migrate` が通る。scraper が JST で動く。既存テストが全部通る |
| B. 共通処理 | `utils/ports.py`、`utils/port_notice.py`、`BaseScraper.parse_departures` / `_upsert_departures` | 単体テストが通る（定型の注意書きで誤検出0件を含む） |
| C. マリックスライン | 詳細ページの取得・解析、予備ルート | fixture のテストで SC-008 を確認 |
| D. マルエーフェリー | 日付形式の修正、方向別の便有無、港別検索、船の対応付け、確定と削除のルール、検索件数の抑制 | fixture のテストで US4 のシナリオ1〜9 を確認 |
| E. Web | Repository、Builder、Controller、テンプレート、バッジの共通化、トップのリンク | PHPUnit で US1 のシナリオ1〜7 を確認。`/`・`/company/{id}` の既存テストが通る |

各 Phase が終わるごとにコミットする（constitution V）。

---

## リスクと対策

| リスク | 対策 |
|---|---|
| マルエーの港別情報の文言が想定と違う（実例が無い） | 拾えなかったら船ステータスで表示する（取りこぼし側に倒す）。`port_notice_unmatched` を warning に出す。元のテキストを保存しておく。quickstart に改善の手順を書いた |
| マルエーの検索結果の HTML や日付形式が変わる | `table.s-result` が無い、または日付を解析できないときは、港別の行を作らずに warning を出す。航路単位は今の安全側の判定（便あり）を続ける |
| マリックスの詳細ページの構造が変わる | 便全体のステータスと日数オフセットの予備ルートで表示を続ける |
| 相手サイトへの負荷 | research R8 の件数を抑える工夫。`requests` の既存のリトライ設定を使う |
| 既存のマルエーの表示が「便なし」に変わって戸惑う | 正しい挙動として spec の Assumptions に書いた。PR の説明にも書く |
