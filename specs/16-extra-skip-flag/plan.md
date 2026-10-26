# Implementation Plan: 臨時便の抜港をスクレイパーが行のフラグで持つ

**Branch**: `16-extra-skip-flag` | **Date**: 2026-10-27 | **Spec**: [spec.md](spec.md) | **Issue**: #96

---

## Summary

スクレイパーが臨時便の港の行ごとに「この港を出たあと、運航の最後の港までに抜港があるか」（`departure_statuses.skips_ports_after`）を書き、Web は今日の臨時便の行のフラグを読むだけにする。15 で足したボードからの逆算（`PortBoard::extraSkipsPortsOf()` など）は消す。

- DB：`skips_ports_after` を足す（R1）
- スクレイパー：マルエー（R2）・マリックス（R3）で書く。Base はハッシュと upsert（R4）
- Web：Entity → `PortBoardEntry` → `PortBoardDay::firstExtraDepartureOf()`（R5）。逆算の処理と `noServiceShipNames`・`isCalling()` を消す
- 15 の契約・research に上書きの注記（R6）

---

## Technical Context

**Language/Version**: Python 3.12（スクレイパー）、PHP 8.3 + Symfony 7.4（Web）
**Primary Dependencies**: SQLAlchemy・BeautifulSoup4、Doctrine ORM・Doctrine Migrations・Twig
**Storage**: MySQL 8.0。`departure_statuses` に列を1つ足す
**Testing**: pytest（`test_marue_ferry.py`・`test_marix_line.py`・`test_base_upsert.py`）、PHPUnit（`PortBoardDayTest`・`PortBoardBuilderTest`・`PortBoardTest`・`PortBoardEntryTest`・`StatusControllerTest`）、`make check-schema`
**Target Platform**: Docker Compose（本番はさくら VPS の `compose.prod.yml`。app の entrypoint がマイグレーションを流し、scraper は app が healthy になってから起動する）
**Project Type**: スクレイパー + Web アプリ
**Performance Goals**: DB の読み取りは増えない。Web の判定はボード4日分の走査から、今日の行の走査だけになる
**Constraints**:
- 臨時便でない行の内容・ハッシュを変えない（FR-010・SC-004）
- 「・抜港あり」の文言・位置・時刻は 15 のまま（FR-007）
- 臨時便が無い日の表示・通知メールは変えない（FR-009）
**Scale/Scope**: マイグレーション1つ、`models.py`・`base.py`・`marue_ferry.py`・`marix_line.py`、`DepartureStatus.php`・`PortBoardEntry.php`・`PortBoardBuilder.php`・`PortBoardDay.php`・`PortBoard.php`・`PortBoardExtraDeparture.php`・`StatusController.php` とそのテスト

未解決の NEEDS CLARIFICATION は無い。

---

## Constitution Check

| Gate | Status | 備考 |
|---|---|---|
| I. スクレイパーは `BaseScraper` 継承・会社ごとに独立 | ✅ PASS | 抜港の判断は会社ごとのスクレイパーの中。Base は列を書くだけ |
| II. Twig + Controller、API なし、スクレイパーは DB に直接書く | ✅ PASS | スクレイパーが DB に書き、Web は読むだけ |
| III. `raw_html_hash`・キーごとの最新状態・`scraper_logs` | ✅ PASS | キーは変えない。`content_hash` は True のときだけ足す（R4） |
| IV. Docker で完結 | ✅ PASS | マイグレーションは `make migrate`・本番の entrypoint |
| V. フェーズごとにコミット | ✅ PASS | Phase A〜D を tasks.md のグループにして、グループごとにコミットする |
| 技術スタック（変更禁止） | ✅ PASS | 変更なし |

**Phase 1 設計の後に再チェック**: 違反なし。Governance の「負債は即日解消」に沿って、15 の割り切りを消す。

---

## Project Structure

### Documentation

```
specs/16-extra-skip-flag/
├── spec.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/ui-status.md      # 「・抜港あり」の決め方（15 を上書き）
├── checklists/requirements.md
├── plan.md                     ← このファイル
└── tasks.md                    （/speckit.tasks で生成）
```

### 変更対象

```
app/migrations/Version20261027000000.php     # 新規
app/src/Entity/DepartureStatus.php
app/src/Service/PortBoardBuilder.php
app/src/View/PortBoardEntry.php
app/src/View/PortBoardDay.php
app/src/View/PortBoard.php
app/src/View/PortBoardExtraDeparture.php
app/src/Controller/StatusController.php
app/tests/{View,Service,Controller}/...
scraper/scraper/db/models.py
scraper/scraper/scrapers/base.py
scraper/scraper/scrapers/marue_ferry.py
scraper/scraper/scrapers/marix_line.py
scraper/tests/test_base_upsert.py・test_marue_ferry.py・test_marix_line.py
specs/15-extra-voyage-badge/contracts/ui-status.md・research.md   # 注記
```

---

## Phases

### Phase A：列とスクレイパーの土台（R1・R4）

- マイグレーション `Version20261027000000`（up：ADD、down：DROP）
- `DepartureStatus`（Entity）に `skipsPortsAfter` と getter/setter
- `models.py` に `skips_ports_after`
- `base.py`：`_departure_hash()` は True のときだけ payload に足す。`_upsert_departures()` の INSERT・UPDATE で書く
- テスト（`test_base_upsert.py`）：False の行のハッシュが今と同じ（固定値で比べる）／True で書かれる／False → True で更新される
- `make migrate`・`make check-schema`

### Phase B：マルエー・マリックス（R2・R3、US1・FR-001〜FR-005）

- マルエー：`_extra_records()` で `skips_ports_after` を詰める。定期便（便検索）の行は False
- マリックス：`_parse_detail_departures()` で臨時便の `no_status` の港を集め、行ごとに詰める。定期便の行と予備ルートの行は False
- テスト
  - マルエー：10/27 波之上（鹿児島・名瀬 True、本部 False）／終点の1個前の名瀬を抜く上り（全行 True）／全港に寄る臨時便（全行 False）／便検索とぶつかった港を挟んでも抜港にしない
  - マリックス：9/6（鹿児島発・名瀬〜本部 no_status）→ 鹿児島 True／9/7 → 那覇 True・名瀬 False／9/27 → 名瀬 False／定期便の行は False
  - `test_marix_line.py`・`test_marue_ferry.py` の既存のフィクスチャ（`scraper/tests/fixtures`）を使う

### Phase C：Web を読み取りにする（R5、US2・FR-006〜FR-008）

- `PortBoardBuilder` で `skipsPortsAfter` を詰め、`$hidden`・`noServiceShipNames` を消す
- `PortBoardEntry`：`skipsPortsAfter` を足し、`noServiceShipNames`・`isCalling()` を消す
- `PortBoardDay::firstExtraDepartureOf()` で `skipsPorts` を決める
- `PortBoard`：`extraSkipsPortsOf()`・`isPortIn()`・`callsAt()` を消す。`PortBoardExtraDeparture::withSkipsPorts()` を消す
- `StatusController::routesWithExtra()`：`$portIds` と呼び出しを消す（使わなくなった `use` も）
- テスト
  - `PortBoardDayTest`：フラグのある臨時便の行で `skipsPorts` が true／無ければ false／状態が欠航の行のフラグは数えない／ほかの会社・ほかの方向の行は数えない
  - `PortBoardBuilderTest`：`skipsPortsAfter` が渡る（`noServiceShipNames` のテストを置き換え）
  - `PortBoardTest`・`PortBoardEntryTest`：逆算・`isCalling()` のテストを消す
  - `StatusControllerTest`：10/27 の「・抜港あり」のテストは、名瀬の行にフラグを立てる形に直す。フラグが無ければ出ない

### Phase D：文書と仕上げ（R6・FR-011）

- 15 の `contracts/ui-status.md`・`research.md` R3 に「16-extra-skip-flag で変更」の注記とリンク
- `make test-php`・`make test-scraper`・`make phpstan`・`make cs-php`・`make lint-php`・`make lint-scraper`・`make check-schema`

---

## Complexity Tracking

| 増えるもの | なぜ要るか | もっと簡単な案を採らない理由 |
|---|---|---|
| 列1つ（行ごとのフラグ） | 寄らない港の情報は、スクレイパーが行を作らないので DB に残らない | 逆算は割り切りが多く（spec 概要の表）、運航ごとの1値は前日に通った港で誤表示する（R1） |

減るもの：`PortBoard` の逆算（約100行）とそのテスト、`noServiceShipNames` の持ち回り、`isCalling()`。
