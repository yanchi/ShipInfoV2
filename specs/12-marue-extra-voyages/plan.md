# Implementation Plan: マルエーフェリーの臨時便を港別ステータスに出す

**Branch**: `12-marue-extra-voyages` | **Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

---

## Summary

船の詳細ページの【臨時便(上り/下り)】を読み、出港時刻のある港ごとに `departure_statuses` の行を作る。行の状態は新しい状態「臨時便」（`extra`）。

- スクレイパー
  - 臨時便を読む（R1〜R3）
  - 行を作る（R4・R7）
  - 取りやめで消す（R6）
  - 臨時便の行は `source_url` で見分ける。定期便の判定・便検索の整理には混ぜない（R5・R6）
  - 臨時便の告知は港別情報に使わない（R8）
- Web
  - `OperationStatusEnum::Extra` を足す（バッジ・凡例・異常の要約・注意書き）
  - トップの会社カードに「◆ 臨時便 鹿児島 16:00発」を出す（R9）
  - 通知メールは Enum から自動で載る（US4）
- DB のスキーマは変えない

---

## Technical Context

**Language/Version**: Python 3.12（スクレイパー）、PHP 8.3 + Symfony 7.4（Web）
**Primary Dependencies**: requests, BeautifulSoup4 (lxml), SQLAlchemy 2.0 / Doctrine ORM, Twig
**Storage**: MySQL 8.0。スキーマの変更なし（`departure_statuses.status` は VARCHAR(32)）
**Testing**: pytest（2026-10-26 の波之上の詳細ページを fixture にする）、PHPUnit
**Target Platform**: Docker Compose（本番はさくら VPS の `compose.prod.yml`）
**Project Type**: スクレイパー ＋ Web アプリ
**Performance Goals**: HTTP リクエストは増えない（詳細ページはもう毎回取っている）。DB の読み取りは、臨時便のある船ごとに1回増える
**Constraints**:
- `BaseScraper.fetch()` / `parse()` / `parse_departures()` のシグネチャは変えない
- 便検索から作る行の結果は変えない（SC-004）。変えてよいのは、臨時便の行を判定から除く分だけ
- Base の変更は `replace_scope` を同じ `source_url` に絞るだけ（今使っているのはマルエーの便検索の行だけ）
- PHP の Enum が先に入っていないと、`extra` の行で Doctrine が落ちる。PHP とスクレイパーは同じデプロイで出す。戻すときは先に `extra` の行を消す（R10）
**Scale/Scope**: `marue_ferry.py`・`port_notice.py`・`base.py`・`models.py`、PHP の Enum・View・Controller・テンプレート3〜4つとテスト

未解決の NEEDS CLARIFICATION は無い。

---

## Constitution Check

| Gate | Status | 備考 |
|---|---|---|
| I. スクレイパーは `BaseScraper` 継承・会社ごとに独立 | ✅ PASS | 臨時便の読み取り・消し方は `MarueFerry` の中。Base は `replace_scope` を同じ出どころに絞るだけで、会社固有の決まりは入れない |
| II. Twig + Controller、API なし、スクレイパーは DB に直接書く | ✅ PASS | 画面は Twig と Controller に1行足すだけ |
| III. `raw_html_hash`・キーごとの最新状態・`scraper_logs` | ✅ PASS | キー（航路×港×出港日×船）は今のまま。臨時便の行もキーごとに1行。`raw_html_hash` は変えない（航路単位は変えないため）。読めない・ぶつかったは警告ログに出す |
| IV. Docker で完結 | ✅ PASS | マイグレーション・新しいライブラリなし |
| V. フェーズごとにコミット | ✅ PASS | 下の Phase A〜E を tasks.md のグループにして、グループごとにコミットする |
| 技術スタック（変更禁止） | ✅ PASS | 変更なし |

**Phase 1 設計の後に再チェック**: 違反なし。新しい状態 `extra` は `skipped`（9-marue-port-skip）と同じく、港の行だけで使う状態として足す。原則 III の「キーごとの最新状態」は崩れない。ただし同じキーに定期便と臨時便が重なるときは、臨時便を詳細の文で伝えるだけになる（R7）。キーを変えるのはマイグレーションと画面の作り直しが要るので、やらない。

---

## Project Structure

### Documentation

```
specs/12-marue-extra-voyages/
├── spec.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── ui-status.md            # 臨時便のバッジ・トップの会社カード
│   └── notification-mail.md    # 通知メール（Enum から自動で載る）
├── samples/                    # 2026-10-26 の波之上の詳細ページ（証跡）
├── checklists/requirements.md
├── plan.md                     ← このファイル
└── tasks.md                    （/speckit.tasks で生成）
```

### 変更対象

```
scraper/scraper/db/models.py                       # OperationStatusEnum.extra
scraper/scraper/scrapers/base.py                   # replace_scope を同じ source_url に絞る（R6）
scraper/scraper/scrapers/marue_ferry.py            # R1〜R7、docstring
scraper/scraper/utils/port_notice.py               # 臨時便の告知を本文から除く（R8）
scraper/tests/test_marue_ferry.py
scraper/tests/test_base_departures.py              # replace_scope と source_url
scraper/tests/test_port_notice.py
app/src/Enum/OperationStatusEnum.php               # Extra
app/src/View/PortBoardEntry.php                    # isAlert に Extra
app/src/View/PortBoardDay.php                      # firstExtraDepartureOf
app/src/View/PortBoardExtraDeparture.php           # 新規（港名・出港時刻）
app/src/Controller/StatusController.php            # routesWithExtra
app/templates/status/_status_badge.html.twig
app/templates/status/_status_legend.html.twig
app/templates/status/_status_warning.html.twig
app/templates/status/index.html.twig
app/templates/_site_styles.html.twig               # status-badge--extra・port-entry--extra・route-extra
app/tests/...                                      # Enum・PortBoardEntry・PortBoardDay・StatusController・IrregularServiceCollector・IrregularStatusMailer
```

---

## Phases

### Phase A：状態「臨時便」を足す（Web が先。R10）

- PHP `OperationStatusEnum::Extra`（label・isIrregular）、Python `OperationStatusEnum.extra`
- バッジ・凡例・注意書き・`isAlert()`・CSS
- テスト：Enum（label・irregularCases に入る）、PortBoardEntry（isAlert・出港済みで薄くしない）、通知の本文に「臨時便」（US4・SC-006）

### Phase B：臨時便を読む（US1・US2 の読み取り）

- `ExtraStop`・`ExtraVoyage`、`_parse_extra_voyages(detail_html, ship)`（R1〜R3）
- 年の決め方を `_parse_voyages()` と共通の関数にする
- テスト：2026-10-26 の fixture で下り3港＋終点・上り6港＋終点が読める。寄港しない港の文が取れる。曜日違い・知らない港・順番違い・途中の港で出港なし・終点なしは None＋警告（SC-005）

### Phase C：行を作る・判定に混ぜない（US1・US2・FR-003・FR-014・FR-015）

- `parse_departures()` の最後に臨時便の行（R4・R7・FR-009）
- `_SEARCH_ROWS` を `_recorded_voyages()`・`_recorded_voyage()`・`_recorded_search_keys()`・`_needs_far_search()` に足す（R5）
- `port_notice._detail_body()` で臨時便の段落を飛ばす（R8）
- テスト
  - SC-001：9行。日付・出港時刻・`scheduled_arrival_at`（終点の入港）・`source_url`
  - SC-002：10/26〜10/27 の亀徳・和泊・与論の下りは0行
  - SC-007：臨時便の行が DB にあっても、10/25 鹿児島発の定期便の判定（今の便・出港済み・前回の記録）が変わらない
  - 定型の注意書きのある詳細ページでも、臨時便の「寄港いたしません」が定期便の抜港にならない
  - 抜粋に「■10月28日（水）那覇港発上り便…欠航」があれば臨時便の行が cancelled
  - 便検索に同じキーがあれば作らず、出港時刻が違えば詳細に「（臨時便 HH:MM発あり）」
  - 2日先以降で臨時便の行だけがあるキーも、間隔どおり便検索する
  - 範囲外の日付は作らない

### Phase D：消す（US3・FR-008・FR-013）

- Base の `replace_scope` を同じ `source_url` に絞る（R6）
- `MarueFerry._upsert_departures()` で、取りやめた臨時便の行を消す（R6）
- テスト
  - 出港前に告知が消えたら全港消える
  - 始発港を出港後に消えたら全港残る（US3-3）
  - 詳細ページが取れなかった回・読めなかった回は消さない
  - 同じ港・日付の便検索にほかの船だけ出ても消えない（US3-4）
  - 時刻が変わったら更新、出港済みの港は更新しない（US3-5）
  - Base：別の `source_url` の行は `replace_scope` で消えない

### Phase E：トップの会社カード（US5）と文書

- `PortBoardExtraDeparture`、`PortBoardDay::firstExtraDepartureOf()`、`StatusController` の `routesWithExtra`、`index.html.twig` の1行（R9）
- テスト
  - PortBoardDay：いちばん早い Extra を選ぶ、無ければ null、ほかの会社・方向は見ない
  - StatusController：トップに「◆ 臨時便 鹿児島 16:00発」、航路のバッジは欠航のまま
  - 異常の要約に臨時便が入る（FR-017）
- docstring（`marue_ferry.py` 冒頭の処理の流れ）、CLAUDE.md は変えない
- `make test-scraper`・`make lint-scraper`・`make test-php`・`make phpstan`・`make cs-php`・`make lint-php`

---

## Complexity Tracking

| 増えるもの | なぜ要るか | もっと簡単な案を採らない理由 |
|---|---|---|
| `MarueFerry._upsert_departures()` の上書き | 臨時便の行を便ごとの出港済みで消す（FR-008） | `replace_source` は港ごとに消すので、便の途中で告知が消えたときに、まだ寄っていない港の行まで消える |
| `replace_scope` を `source_url` で絞る（Base） | 便検索の整理で臨時便の行が消える（FR-013） | 臨時便の行にも `replace_scope` を付けると、詳細ページが取れなかった回に、便検索の整理で消える |
