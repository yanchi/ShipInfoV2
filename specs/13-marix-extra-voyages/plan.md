# Implementation Plan: マリックスラインの臨時便を港別ステータスに出す

**Branch**: `13-marix-extra-voyages` | **Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

---

## Summary

マリックスラインの一覧・詳細ページで、公式が臨時便の印を付けた便を見分けて読む。臨時便が寄る港の行を、状態「臨時便」（`extra`）で書く。

- スクレイパー（`marix_line.py`）
  - 便の種類（臨時便・定期便・分からない）を決める（R1）。名瀬発などの方向を決める（R2）
  - 寄る港だけ「臨時便」の行にする。寄らない港は作らない（R3）
  - 同じキーの定期便（欠航）より臨時便を優先する。同じ回は並び順に関係なく決める（R4）。前の回の行は、詳細ページが取れない回と出港済みのときだけ守る（R5）
  - 臨時便の詳細ページが取れなければ、予備ルートは使わない（R6）
  - 臨時便の詳細ページを読めた回は、その臨時便が書かなくなった行を消す（R7）
  - 航路単位は定期便だけで決める。分からない便は書かないが、「便なし」にもしない（R8）
- Base（`base.py`）
  - 行を消す前に flush する（R10。本番の `autoflush=False` 対策）
- Web
  - トップの会社カードで、臨時便以外の行が無い日のバッジを「臨時便」にする（R9）
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
**Performance Goals**: HTTP リクエストは増えない（臨時便の詳細ページも、一覧にある便として今も取っている）。DB の読み取りは1回増える（R5 の `extra` の行）。後始末（R7）の SELECT は、読めた臨時便の URL ごとに1回
**Constraints**:
- Base の変更は、消す前の flush の1行だけ（R10）。臨時便の決まりは `MarixLine` の中だけ（原則 I）
- 臨時便の無い日の結果は変えない（FR-013・SC-006）。今のマリックスラインのテストはそのまま通る。ただし、詳細ページが取れない便の航路単位は書かなくなる（R8。今までのテストで、詳細ページが取れない便の航路単位を確かめているものは無い）
- 一覧に載った臨時便の HTML は未確認。一覧のクラスが推測と違っても、詳細ページで見分けられるようにする（R1）
- 本番の `SessionLocal` は `autoflush=False`。テストの `db_session` は既定の `autoflush=True`。消す処理のテストは `db_session.autoflush = False` にして本番と同じ条件で確かめる（R10）
**Scale/Scope**: `marix_line.py`・`base.py` とそのテスト、`StatusController.php`・`PortBoardDay.php` とそのテスト

未解決の NEEDS CLARIFICATION は無い。

---

## Constitution Check

| Gate | Status | 備考 |
|---|---|---|
| I. スクレイパーは `BaseScraper` 継承・会社ごとに独立 | ✅ PASS | 臨時便の決まりは `MarixLine` の中だけ。`_upsert_departures()` は上書きして Base の処理を呼んだ後に足す。Base の変更は flush の1行で、会社固有の決まりは入れない |
| II. Twig + Controller、API なし、スクレイパーは DB に直接書く | ✅ PASS | Controller の条件を1つと、View のメソッドを1つ足すだけ |
| III. `raw_html_hash`・キーごとの最新状態・`scraper_logs` | ✅ PASS | キー（航路×港×出港日×船）は今のまま。同じキーは1本に絞る（R4・R5）。`raw_html_hash` は一覧の HTML のまま。分からない便は航路単位を書かないので、ハッシュで古い「不明」が残ることも無い（R8）。ぶつかった・読めないは警告ログに出す |
| IV. Docker で完結 | ✅ PASS | マイグレーション・新しいライブラリなし |
| V. フェーズごとにコミット | ✅ PASS | 下の Phase A〜F を tasks.md のグループにして、グループごとにコミットする |
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
│   └── ui-status.md            # 臨時便以外の行が無い日のトップのバッジ
├── samples/                    # 2026-08〜09 の公式の詳細ページ（証跡。style・script を抜いたもの）
├── checklists/requirements.md
├── plan.md                     ← このファイル
└── tasks.md                    （/speckit.tasks で生成）
```

### 変更対象

```
scraper/scraper/scrapers/base.py                   # 消す前に flush（R10）
scraper/scraper/scrapers/marix_line.py             # R1〜R8、docstring
scraper/tests/test_base_departures.py              # autoflush=False で消す処理
scraper/tests/test_marix_line.py
scraper/tests/fixtures/marix/extra_*.html          # 新規（samples/ と同じもの。quickstart.md の表）
scraper/tests/fixtures/marix/*_20260906.html
scraper/tests/fixtures/marix/*_20260907.html
app/src/View/PortBoardDay.php                      # hasRegularDeparturesOf（R9）
app/src/Controller/StatusController.php            # routesDepartingMidway（R9）
app/tests/...                                      # PortBoardDay・StatusController（トップのバッジ）
```

---

## Phases

### Phase A：便の種類と、臨時便の寄る港の行（US2・US3・FR-001〜FR-004・FR-010）

- `_STATUS_BY_CLASS["temporary"] = extra`、`_voyage_kind()`（R1）
- 臨時便は `voyage_status = extra` で `_departures_from_detail()` に渡し、`no_status` の港は作らない（R3）
- 臨時便の詳細ページが取れなければ行を作らない（R6）
- 臨時便の行に `extra_voyage: True`
- テスト
  - SC-002：9/6 の臨時便で、鹿児島（9/6 09:00）が `extra`、到着予定は 9/7 05:00。寄らない5港は0行
  - SC-003 の後半：9/27 の臨時便で、8/25 の行は0行
  - 一覧のクラスに `temporary` が無くても、詳細ページの見出し・港で臨時便とわかる（R1）
  - 種類 `unknown`：一覧のクラスが `route alert` で詳細ページが 500 → 予備ルートの行（今までどおり）
  - 詳細に h2（「臨時便で時間を変更し…」）が入る
  - 臨時便の港が `cancel` なら `cancelled`
  - `unknown_status_class`・`detail_status_unknown` を出さない

### Phase B：Base の flush と、臨時便の行の後始末（US3・FR-011・R7・R10）

- Base：消す前に flush
- `MarixLine._upsert_departures()`：flush → 読めた臨時便の URL ごとに、今回書かなかった行を消す
- テスト（`db_session.autoflush = False`）
  - Base：同じ回に `source_url` を書き換えた行が、古い `source_url` の `replace_source` で消えない
  - 寄らなくなった港（名瀬が `no_status` になった）の臨時便の行が消える（US3-3）
  - 臨時便の出港日がずれたら、古い日付の行が消える
  - 種類 `unknown` の回に作った予備ルートの行（臨時便の URL・船名なし）が、読めた回に消える

### Phase C：同じキーの優先（US1・FR-005〜FR-007）

- `_extra_rows_kept()`、`_resolve_extra_conflicts()`（R4・R5）
- テスト（`db_session.autoflush = False`）
  - SC-001：9/7 の一覧を2通りの並び順で読んで、那覇（07:00）・名瀬（21:20）のクロスが `extra`。本部・与論・和泊・亀徳のクロスは `cancelled`
  - US1-4：臨時便が一覧にあり詳細ページが取れない回、定期便（欠航）が上書きしない
  - US1-5：臨時便が出港後に一覧から消えた回、上書きしない
  - US1-6：臨時便が出港前に一覧から消えた回、定期便の欠航に戻る
  - 定期便が通常運航で同じキーの臨時便があれば、定期便の行に「（臨時便 HH:MM発あり）」と警告
  - 臨時便の出港日がずれたら、古い日付の行は定期便の欠航に戻る（R5・R7）
  - SC-008：定期便の詳細ページが取れない回も、予備ルートの行は今までどおり作る（9/6 のプラスの鹿児島が消えない）

### Phase D：方向（US4・FR-009）

- `_parse_direction()` に一覧の欄・行き先を足す（R2）
- テスト
  - SC-003 の前半：上りの欄の「名瀬港発 鹿児島新港向け」で、上りの名瀬（9/27 05:50）が `extra`。終点の鹿児島は作らない
  - 欄も始発港も行き先も無ければ `direction_unknown` で読み飛ばす（今のまま）

### Phase E：航路単位（US5・FR-008）

- `parse()` で、臨時便は飛ばし、分からない便は書かずに最後に `seen` に入れる（R8）
- テスト
  - SC-004：9/6・9/7 の一覧を2通りの並び順で読んで、航路単位が 9/6 下り `delayed`・9/7 上り `cancelled`。`unknown` は0件
  - 臨時便しか無い今日は `no_service`
  - SC-009：分からない便がその方向の今日の唯一の便なら、航路単位を書かない（`no_service` も書かない）。分からない便が先で同じ日の定期便が後ろでも、定期便で書く

### Phase F：トップのバッジ（US4・FR-014）と文書

- `PortBoardDay::hasRegularDeparturesOf()`、`StatusController::routesDepartingMidway()`（R9）
- テスト
  - SC-007：航路単位が `no_service` で、今日の下りが始発港の臨時便（鹿児島 10:00）だけなら、バッジが「◆ 臨時便」で、下に「◆ 臨時便 鹿児島 10:00発」
  - 始発港に臨時便以外の行があれば、今までどおり（「— 便なし」）
  - 途中の港を出る定期便があれば、今までどおり（12 のテストが通る）
  - 航路単位が欠航なら、バッジは欠航のまま
- SC-005（9/7 のトップと通知メール）を確かめる
- `marix_line.py` 冒頭の docstring
- `make test-scraper`・`make lint-scraper`・`make test-php`・`make phpstan`・`make cs-php`・`make lint-php`

---

## Complexity Tracking

| 増えるもの | なぜ要るか | もっと簡単な案を採らない理由 |
|---|---|---|
| `_resolve_extra_conflicts()` で DB を読む（R5） | 臨時便の詳細ページが取れない回・出港後に一覧から消えた回に、定期便の欠航で上書きしない（FR-007） | この回の行だけで決めると、臨時便が「欠航」へ戻る |
| `MarixLine._upsert_departures()` の上書き（R7） | 寄らなくなった港・出港日がずれた日・分からなかった回の予備ルートの、臨時便の古い行を消す（FR-011） | Base の `replace_source` は、その回に書いた港の分しか登録されない。臨時便は `no_status` の港を書かないので、寄らなくなった港の行が残る |
| 便の種類に `unknown` を足す（R1・R8） | 詳細ページが取れない臨時便が、定期便として航路単位を書いたり、「便なし」になったりするのを防ぐ（FR-008） | 一覧のクラスだけで決めると、一覧に `temporary` が無いときに臨時便を定期便と取り違える |
| Base の flush（R10） | 本番の `autoflush=False` で、同じ回に上書きした行を消してしまう | テストの `db_session` を一律で `autoflush=False` にすると既存テストが落ちる。それはこの機能の範囲外 |
