# Implementation Plan: 抜港を「抜港」と表示する

**Branch**: `9-marue-port-skip` | **Date**: 2026-10-06 | **Spec**: [spec.md](spec.md)

---

## Summary

港の行のステータスに「抜港」（`skipped`）を足して、欠航と分けて出す。

- **共通**：PHP・Python の `OperationStatusEnum` に `skipped`（文言「抜港」）を足す。DB は変えない（`departure_statuses.status` は VARCHAR）
- **マルエーフェリー**
  - 抜港と読み取った港を `cancelled` → `skipped` にする
  - 「寄港いたしません」なども抜港として読む。港名の後ろの括弧書きで列挙が切れる不具合も直す
  - 船ブロックのタグを全部読む
- **マリックスライン**：詳細ページの `no_status`（寄港しません）を `cancelled` → `skipped` にする
- **Web・通知**：バッジ `≫ 抜港`（オレンジ）、異常の要約・行の強調・凡例・注意書きに入れる。通知メールは enum から自動で「抜港」になる

---

## Technical Context

**Language/Version**: Python 3.12 / PHP 8.3
**Primary Dependencies**: requests, BeautifulSoup4 (lxml), SQLAlchemy 2.0 / Symfony 7.4, Doctrine ORM, Twig
**Storage**: MySQL 8.0。スキーマの変更なし（research R1）
**Testing**: pytest（2026-10-06 の保存版を fixture にする）/ PHPUnit
**Target Platform**: Docker Compose（本番はさくら VPS の `compose.prod.yml`）
**Project Type**: スクレイパー + Web アプリ（MVP、Twig）
**Performance Goals**: 変わらない（取得するページ・検索の回数は増やさない）
**Constraints**:
- `BaseScraper.fetch()` / `parse()` / `parse_departures()` のシグネチャは変えない
- 航路単位（`operation_statuses`）には `skipped` を書かない（FR-011。MySQL の ENUM に無い値でもある）
- 既存のステータスの文言・見た目は変えない（FR-012）
**Scale/Scope**: 港の行のステータスの種類が1つ増えるだけ。行の数は変わらない

未解決の NEEDS CLARIFICATION は無い（research.md で全部解決済み）。

---

## Constitution Check

| Gate | Status | 備考 |
|---|---|---|
| I. スクレイパーは `BaseScraper` 継承・会社ごとに独立 | ✅ PASS | 変更は各社のクラスと共通の `utils/port_notice.py` の中だけ。Base は変えない |
| II. Twig + Controller、API なし、スクレイパーは DB に直接書く | ✅ PASS | 画面はテンプレートと View の変更だけ |
| III. `raw_html_hash`・キーごとの最新状態・`scraper_logs` | ✅ PASS | 書き方は変えない。過去の `cancelled` の行はさかのぼって直さない（次の実行で内容が変われば上書き）。新しい warning（`search_datetime_missing` など）は構造化ログに出す |
| IV. Docker で完結 | ✅ PASS | マイグレーションなし。新しいライブラリなし |
| V. フェーズごとにコミット | ✅ PASS | 下の Phase A〜D を tasks.md のグループにして、グループごとにコミットする |
| 技術スタック（変更禁止） | ✅ PASS | 変更なし |

**Phase 1 設計の後に再チェック**: 違反なし。`OperationStatusEnum` を航路と港で共有したまま値を足すトレードオフは research R1 に書いた（航路単位に `skipped` が入らないことをテストで縛る）。

---

## Project Structure

### Documentation

```
specs/9-marue-port-skip/
├── spec.md
├── research.md
├── data-model.md
├── contracts/
│   ├── ui-status.md
│   └── notification-mail.md
├── quickstart.md
├── samples/                 # 2026-10-06 の保存版（証跡）
├── plan.md                  ← このファイル
└── tasks.md                 （/speckit.tasks で生成）
```

### 変更対象

```
scraper/scraper/db/models.py                       # OperationStatusEnum に skipped
scraper/scraper/utils/port_notice.py               # skip の表現を増やす（R2）、括弧書きを取り除いて読む（R3）
scraper/scraper/scrapers/marue_ferry.py            # 全タグ（R4）、言及の無い港（R5）、skip → skipped、日時なし・0件の抜港（R6）、docstring
scraper/scraper/scrapers/marix_line.py             # no_status → skipped（R7）、docstring
scraper/tests/fixtures/marue/kagoshima_20261006.html           # 新規（samples のコピー）
scraper/tests/fixtures/marue/ship_detail_naminoue_20261006.html # 新規（samples のコピー）
scraper/tests/test_port_notice.py                  # 表現・括弧書き・仮定の文
scraper/tests/test_marue_ferry.py                  # 保存版・寄港いたしません版・タグの順・欠航優先・日時なし／0件
scraper/tests/test_marix_line.py                   # no_status → skipped、欠航の便は欠航のまま

app/src/Enum/OperationStatusEnum.php               # Skipped（抜港、isIrregular）
app/src/View/PortBoardEntry.php                    # isAlert() に Skipped
app/templates/status/_status_badge.html.twig       # ≫ 抜港
app/templates/status/_status_legend.html.twig      # 凡例に抜港
app/templates/status/_status_warning.html.twig     # 抜港でも注意書き
app/templates/_site_styles.html.twig               # status-badge--skipped / port-entry--skipped
app/src/DataFixtures/AppFixtures.php               # 抜港のサンプル行（画面確認用）
app/tests/Enum/OperationStatusEnumTest.php
app/tests/View/PortBoardEntryTest.php
app/tests/Service/PortAlertSummaryBuilderTest.php
app/tests/Service/IrregularServiceCollectorTest.php
app/tests/Service/IrregularStatusMailerTest.php
app/tests/Controller/StatusControllerTest.php

specs/5-ui-readability/contracts/ui-status.md      # 表に抜港の行を足す（このspecの contracts/ui-status.md へのリンク）
```

---

## Phase 0: Research 結果

→ [research.md](research.md)

| # | 決めたこと |
|---|---|
| R1 | 既存の `OperationStatusEnum` に `skipped` を足す。マイグレーションなし。航路単位には書かない |
| R2 | skip の表現：抜港・寄港(いたし／致し／し)ません・寄港(を／は)(取りやめ／取り止め／見合わせ／中止)。仮定の文の除外は今のまま |
| R3 | 括弧書きを取り除いてから読む（保存版の「和泊港(沖永良部島)・与論港(与論島)」で和泊を取りこぼす不具合） |
| R4 | タグは全部読む。status は一番重いもの、conditional / schedule_changed はどれか1つにあれば |
| R5 | 条件付＋スケジュール変更の船は、言及の無い港を通常運航にしない（時刻が変わっているため） |
| R6 | 便検索で日時が読めない・0件でも、今の便の抜港の港なら `skipped` の行を作る |
| R7 | マリックスの `no_status` → `skipped`。便が欠航・運休ならそちら |
| R8 | バッジ `≫ 抜港`、背景 `#ffe0c2`・文字 `#8a3b00` |
| R9 | 通知メールは enum の変更だけで「抜港」になる |
| R10 | 保存版を fixture にコピー。「寄港いたしません」だけ版はテストの中で作る |

---

## Phase 1: 設計

→ [data-model.md](data-model.md) / [contracts/ui-status.md](contracts/ui-status.md) / [contracts/notification-mail.md](contracts/notification-mail.md) / [quickstart.md](quickstart.md)

### port_notice.py

```
extract_port_notices(text, resolver):
  for sentence in _sentences(text):
    if 仮定の文: continue
    parsed = _strip_parentheses(sentence)        # (…) と （…） を消す。入れ子は考えない
    for notice in _sentence_notices(parsed, resolver, original=sentence): ...
```

- `_keyword_pos(text, "skip")`：`_SKIP_PATTERN.search(text)` の開始位置
- `_kinds()` の判定も同じ正規表現を使う

### marue_ferry.py

- `_parse_ships()`：`block.select("div.tag-list span")` を全部読む → `ShipInfo(status, conditional, schedule_changed)`
- `_current_voyage_status()`：data-model 4 の 1〜6。skip → `OperationStatusEnum.skipped`
- `_search()`：マルエーの行で日時が読めなければ、行を残して `departure_at=arrival_at=None`（warning）
- `parse_departures()`：
  - 日時 None の行：今の便が同じ船・同じ航路で、その港が抜港で、出港日が合う → `skipped`（時刻なし）。それ以外は書かない
  - 0件のキー：今の便が同じ航路にあり、その港が抜港で、出港日（下船日 − day_offset の差）が合う → `skipped`。それ以外は今の `no_service`

### marix_line.py

- `_departures_from_detail()`：`no_status` → `voyage_status` が欠航・運休ならそれ、でなければ `skipped`

### Web

- enum・`isAlert()`・テンプレート3つ・CSS（contracts/ui-status.md）
- `PortAlertSummaryBuilder`・`IrregularServiceCollector`・通知メールのテンプレートは変えない（enum から決まる）

---

## 実装フェーズ（tasks.md のグループのもと）

| Phase | 内容 | 完了条件 |
|---|---|---|
| A. 共通の値 | PHP・Python の enum に `skipped`。`isIrregular`・`isAlert`。テンプレート・CSS・凡例・注意書き。AppFixtures | PHPUnit で、バッジ・異常の要約・出港済みにならない・通知メールの「抜港」を確認（US1 の 4、US2）。既存テストが全部通る |
| B. 港別情報の読み取り | `port_notice.py` の skip の表現と括弧書き | pytest：US3 の 1〜3、括弧書きの列挙、既存の誤検出0件のテストが通る |
| C. マルエー | 全タグ、言及の無い港、skip → skipped、日時なし・0件の抜港、保存版の fixture | pytest：SC-001（保存版と寄港いたしません版）、SC-003（欠航優先）、SC-004（タグの順） |
| D. マリックス | `no_status` → `skipped`、欠航の便は欠航 | pytest：US1 の 2、SC-003 |

A を先にやる（B〜D が `skipped` を書いても画面・通知が「抜港」で出る状態にしておく）。B → C は順番、D は A の後ならいつでもいい。各 Phase が終わるごとにコミットする（constitution V）。

---

## リスクと対策

| リスク | 対策 |
|---|---|
| 「寄港しません」などの表現を広げて、通常運航の日に抜港が増える（SC-005） | 既存の誤検出0件のテスト（定型の注意書き・仮定の文）を全部通す。定型の注意書き「抜港(港に接岸できず…)や港変更になることがあります」は区切り（`台風の影響や`）の後で読まない |
| 括弧書きを消して、括弧の中にしか港名が無い告知を取りこぼす | 港名を括弧の中だけに書く例は見つかっていない。取りこぼしは今の方針（誤判定より取りこぼし）どおり。`port_notice_unmatched` の warning で気づける |
| 条件付＋スケジュール変更の船で、言及の無い港が「条件付・遅延」のままになる（spec の想定と違う可能性） | research R5 に理由を書いた。PR の説明にも書く |
| 日時なし・0件の抜港の判定（R6）は実例が無い | 今の便（`current_voyage`）が決まっているときだけ作る。決まらなければ今までどおり。warning を出す |
| `skipped` が航路単位に入って MySQL の ENUM で書き込みに失敗する | 航路単位を作る経路に `skipped` が無いことを両社のテストで確かめる |
