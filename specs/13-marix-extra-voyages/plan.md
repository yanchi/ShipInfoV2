# Implementation Plan: マリックスラインの臨時便を港別ステータスに出す

**Branch**: `13-marix-extra-voyages` | **Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

---

## Summary

マリックスラインの一覧・詳細ページで、公式が臨時便の印を付けた便を見分けて読む。臨時便が寄る港の行を、状態「臨時便」（`extra`）で書く。

- スクレイパー（`marix_line.py`）
  - 臨時便を見分ける（R1）、名瀬発などの方向を決める（R2）
  - 寄る港だけ「臨時便」の行にする。寄らない港は作らない（R3）
  - 同じキーの定期便（欠航）より臨時便を優先する。同じ回は並び順に関係なく決め（R4）、前の回の行も守る（R5）
  - 予備ルートは臨時便に使わない。臨時便が寄る港に船名なしの行を出さない（R6）
  - 航路単位は定期便だけで決める（R8）
- Web
  - トップの会社カードで、始発港を出る臨時便しか無い日のバッジを「臨時便」にする（R9）
  - それ以外の表示・通知メールは 12 のまま（状態 `extra` の行から自動で出る）
- DB のスキーマは変えない

---

## Technical Context

**Language/Version**: Python 3.12（スクレイパー）、PHP 8.3 + Symfony 7.4（Web）
**Primary Dependencies**: requests, BeautifulSoup4 (lxml), SQLAlchemy 2.0 / Doctrine ORM, Twig
**Storage**: MySQL 8.0。スキーマの変更なし（`extra` は 12 で追加済み）
**Testing**: pytest（2026-08〜09 の公式の詳細ページ6本を fixture にする）、PHPUnit
**Target Platform**: Docker Compose（本番はさくら VPS の `compose.prod.yml`）
**Project Type**: スクレイパー ＋ Web アプリ
**Performance Goals**: HTTP リクエストは増えない（臨時便の詳細ページも、一覧にある便として今も取っている）。DB の読み取りは1回増える（R5・R6 の `extra` の行）
**Constraints**:
- `BaseScraper` は変えない。臨時便の決まりは `MarixLine` の中だけ（原則 I）
- 臨時便の無い日の結果は変えない（FR-013・SC-006）。今のマリックスラインのテストはそのまま通る
- 一覧に載った臨時便の HTML は未確認。一覧のクラスが推測と違っても、詳細ページで見分けられるようにする（R1）
**Scale/Scope**: `marix_line.py` とそのテスト、`StatusController.php` とそのテスト

未解決の NEEDS CLARIFICATION は無い。

---

## Constitution Check

| Gate | Status | 備考 |
|---|---|---|
| I. スクレイパーは `BaseScraper` 継承・会社ごとに独立 | ✅ PASS | 変更は `MarixLine` の中だけ。`_upsert_departures()` は上書きして Base の処理を呼んだ後に足す。Base は変えない |
| II. Twig + Controller、API なし、スクレイパーは DB に直接書く | ✅ PASS | Controller の条件を1つ足すだけ |
| III. `raw_html_hash`・キーごとの最新状態・`scraper_logs` | ✅ PASS | キー（航路×港×出港日×船）は今のまま。同じキーは1本に絞る（R4・R5）。`raw_html_hash` は一覧の HTML のまま。ぶつかった・読めないは警告ログに出す |
| IV. Docker で完結 | ✅ PASS | マイグレーション・新しいライブラリなし |
| V. フェーズごとにコミット | ✅ PASS | 下の Phase A〜E を tasks.md のグループにして、グループごとにコミットする |
| 技術スタック（変更禁止） | ✅ PASS | 変更なし |

**Phase 1 設計の後に再チェック**: 違反なし。同じキーに定期便が走る状態と臨時便が来たら、臨時便は定期便の行の詳細の文で伝えるだけになる（R4）。12 と同じ割り切りで、公式の記録では起きていない。

---

## Project Structure

### Documentation

```
specs/13-marix-extra-voyages/
├── spec.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── ui-status.md            # 臨時便しか無い日のトップのバッジ
├── samples/                    # 2026-08〜09 の公式の詳細ページ（証跡。style・script を抜いたもの）
├── checklists/requirements.md
├── plan.md                     ← このファイル
└── tasks.md                    （/speckit.tasks で生成）
```

### 変更対象

```
scraper/scraper/scrapers/marix_line.py             # R1〜R8、docstring
scraper/tests/test_marix_line.py
scraper/tests/fixtures/marix/extra_*.html          # 新規（samples/ と同じもの。quickstart.md の表）
scraper/tests/fixtures/marix/*_20260906.html
scraper/tests/fixtures/marix/*_20260907.html
app/src/Controller/StatusController.php            # routesDepartingMidway（R9）
app/tests/...                                      # StatusController（トップのバッジ）
```

---

## Phases

### Phase A：臨時便を見分けて、寄る港の行を作る（US2・US3・FR-001〜FR-004）

- `_STATUS_BY_CLASS["temporary"] = extra`、`_is_extra_voyage()`（R1）
- `_departures_from_detail(..., extra=True)`：`no_status` の港は作らない（R3）
- 臨時便の行に `extra_voyage: True`・`replace_source`（R7）
- テスト
  - SC-002：9/6 の臨時便で、鹿児島（9/6 09:00）が `extra`、到着予定は 9/7 05:00。寄らない5港は0行
  - SC-003 の後半：9/27 の臨時便で、8/25 の行は0行
  - 一覧のクラスに `temporary` が無くても、詳細ページの見出し・港で臨時便とわかる（R1）
  - 詳細に h2（「臨時便で時間を変更し…」）が入る
  - 臨時便の港が `cancel` なら `cancelled`
  - `unknown_status_class`・`detail_status_unknown` を出さない

### Phase B：方向と航路単位（US4・US5・FR-008・FR-009）

- `_parse_direction()` に一覧の欄・行き先を足す（R2）
- `parse()` で臨時便を飛ばす（R8）
- テスト
  - SC-003 の前半：上りの欄の「名瀬港発 鹿児島新港向け」で、上りの名瀬（9/27 05:50）が `extra`。終点の鹿児島は作らない
  - SC-004：9/6・9/7 の一覧を2通りの並び順で読んで、航路単位が 9/6 下り `delayed`・9/7 上り `cancelled`。`unknown` は0件
  - 臨時便しか無い今日は `no_service`
  - 欄も始発港も行き先も無ければ `direction_unknown` で読み飛ばす（今のまま）

### Phase C：同じキーの優先（US1・FR-005〜FR-007）

- `_resolve_extra_conflicts()`（R4・R5）
- テスト
  - SC-001：9/7 の一覧を2通りの並び順で読んで、那覇（07:00）・名瀬（21:20）のクロスが `extra`。本部・与論・和泊・亀徳のクロスは `cancelled`
  - 前の回に臨時便の行を書いた後、臨時便が一覧に無い回で、定期便（欠航）が上書きしない（US1-4）
  - 定期便が通常運航で同じキーの臨時便があれば、定期便の行に「（臨時便 HH:MM発あり）」と警告
  - 臨時便の出港日がずれたら、古い日付の行は定期便の欠航に戻る（R7）
  - DB に保存して（`run()`）、1つのキーに1行

### Phase D：予備ルート（FR-010・FR-015）

- 臨時便の詳細ページが取れなければ行を作らない（R6）
- 定期便の予備ルートは、臨時便が寄る港・日付を飛ばす（R6）
- `MarixLine._upsert_departures()` で船名なしの行を消す（R6）
- テスト
  - SC-008：9/7 で定期便の詳細ページが取れない回、那覇・名瀬は臨時便の1行だけ。本部・与論・和泊・亀徳は船名なしの欠航
  - 前の回の船名なしの行が、臨時便を書いた回に消える
  - 臨時便の詳細ページが取れない回は、前回の臨時便の行が残り、予備ルートの行もできない

### Phase E：トップのバッジ（FR-014）と文書

- `StatusController::routesDepartingMidway()`（R9）
- テスト
  - SC-007：航路単位が `no_service` で、今日の下りが始発港の臨時便（鹿児島 10:00）だけなら、バッジが「◆ 臨時便」で、下に「◆ 臨時便 鹿児島 10:00発」
  - 途中の港を出る定期便があれば、今までどおり（12 のテストが通る）
  - 航路単位が欠航なら、バッジは欠航のまま
- `marix_line.py` 冒頭の docstring（臨時便のクラス・見分け方・優先）
- SC-005（9/7 のトップと通知メール）は、12 の表示と通知が状態 `extra` から出るので、Phase C の行のテストと 12 の既存テストで足りる。通知の dry-run で目でも確かめる（quickstart）
- `make test-scraper`・`make lint-scraper`・`make test-php`・`make phpstan`・`make cs-php`・`make lint-php`

---

## Complexity Tracking

| 増えるもの | なぜ要るか | もっと簡単な案を採らない理由 |
|---|---|---|
| `_resolve_extra_conflicts()` で DB を読む（R5） | 臨時便が一覧から先に消えた回に、定期便の欠航で上書きしない（FR-007） | この回の行だけで決めると、臨時便が出港した後に「欠航」へ戻る |
| `MarixLine._upsert_departures()` の上書き（R6） | 定期便の詳細ページが取れない回が続いても、船名なしの行を残さない（FR-015） | Base の `replace_source`・`replace_scope` は同じ `source_url` の行しか消さない。Base を変えると、ほかの会社の行の消し方に響く |
