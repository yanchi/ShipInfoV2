# Implementation Plan: 臨時便がある日の会社カードのバッジを「スケジュール変更」にする

**Branch**: `15-extra-voyage-badge` | **Date**: 2026-10-27 | **Spec**: [spec.md](spec.md)

---

## Summary

今日その方向に臨時便がある航路は、会社カードのバッジが「✓ 通常運航」「○ 運航予定」になるところを「▲ スケジュール変更」にする。臨時便の1行には、臨時便が寄らない港があれば「・抜港あり」を足す。通知メールは、航路が通常運航で港の行に臨時便があれば、状況の頭を「スケジュール変更」にする。

- Web だけを変える。スクレイパー・DB は変えない
  - `StatusController`：航路のバッジを組み立てた後に、臨時便がある航路を `changed` にする（R1・R2）。`routesDepartingMidway` は `routeBadges` に名前を変える
  - `PortBoard`：臨時便の運航に抜港があるかを返す（R3）。`PortBoardExtraDeparture` に `skipsPorts`
  - `index.html.twig`：変数名の変更と「・抜港あり」
  - `IrregularService::statusText()`：臨時便がある日の頭の文言（R4）
- 12・13 の「臨時便は定期便の通常運航と混ざってもスケジュール変更にしない」を、この機能の契約で上書きする（FR-010）

---

## Technical Context

**Language/Version**: PHP 8.3 + Symfony 7.4
**Primary Dependencies**: Doctrine ORM, Twig
**Storage**: MySQL 8.0。スキーマの変更なし
**Testing**: PHPUnit（`StatusControllerTest`・`PortBoardTest`・`IrregularServiceCollectorTest`・`IrregularStatusMailerTest`）
**Target Platform**: Docker Compose（本番はさくら VPS の `compose.prod.yml`）
**Project Type**: Web アプリ
**Performance Goals**: DB の読み取りは増えない。抜港の判定はトップで組み立て済みのボード（4日分）を見るだけ
**Constraints**:
- 臨時便が無い日の表示・メールは変えない（FR-007・SC-003）
- 欠航・運休・条件付・不明・情報なし・便なし・臨時便しか無い日のバッジは変えない（FR-002）
- 会社を問わない（FR-008）
**Scale/Scope**: `StatusController.php`・`PortBoard.php`・`PortBoardExtraDeparture.php`・`index.html.twig`・`IrregularService.php` とそのテスト

未解決の NEEDS CLARIFICATION は無い。

---

## Constitution Check

| Gate | Status | 備考 |
|---|---|---|
| I. スクレイパーは `BaseScraper` 継承・会社ごとに独立 | ✅ PASS | スクレイパーは触らない |
| II. Twig + Controller、API なし、スクレイパーは DB に直接書く | ✅ PASS | Controller と View の変更だけ |
| III. `raw_html_hash`・キーごとの最新状態・`scraper_logs` | ✅ PASS | データは変えない（表示だけ） |
| IV. Docker で完結 | ✅ PASS | マイグレーション・新しいライブラリなし |
| V. フェーズごとにコミット | ✅ PASS | 下の Phase A〜C を tasks.md のグループにして、グループごとにコミットする |
| 技術スタック（変更禁止） | ✅ PASS | 変更なし |

**Phase 1 設計の後に再チェック**: 違反なし。

---

## Project Structure

### Documentation

```
specs/15-extra-voyage-badge/
├── spec.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── ui-status.md            # 会社カードのバッジと臨時便の1行（12・13 の決まりを上書き）
│   └── notification-mail.md    # 状況の文言
├── checklists/requirements.md
├── plan.md                     ← このファイル
└── tasks.md                    （/speckit.tasks で生成）
```

### 変更対象

```
app/src/Controller/StatusController.php        # routeBadges（R1）、routesWithExtra に skipsPorts（R3）
app/src/View/PortBoard.php                     # extraSkipsPortsOf（R3）
app/src/View/PortBoardExtraDeparture.php       # skipsPorts
app/src/View/IrregularService.php              # statusText（R4）
app/templates/status/index.html.twig           # routeBadges、・抜港あり
app/tests/Controller/StatusControllerTest.php
app/tests/View/PortBoardTest.php
app/tests/Service/IrregularServiceCollectorTest.php
specs/12-marue-extra-voyages/contracts/ui-status.md       # 上書きした旨の注記
specs/12-marue-extra-voyages/contracts/notification-mail.md
specs/13-marix-extra-voyages/contracts/ui-status.md
```

---

## Phases

### Phase A：バッジ（US1・FR-001〜FR-003・FR-005）

- `StatusController`：`routesDepartingMidway()` → `routeBadges()`。組み立てた後、今日その方向に臨時便がある航路で、ふだんのバッジが通常運航・運航予定なら `['kind' => 'changed', ...]`（R1・R2）
- `index.html.twig`：`routesDepartingMidway` → `routeBadges`。コメントの「航路単位では便なし」を直す
- テスト
  - SC-001：航路単位が通常運航・途中の港（名瀬 03:50・本部 12:00）に臨時便 → 「▲ スケジュール変更」、注意書きなし、下に「◆ 臨時便 名瀬 03:50発」
  - 臨時便が出港済み（`now` より前）でも「▲ スケジュール変更」（Clarifications）
  - 航路が便なしで途中の港が運航予定＋臨時便 → 「▲ スケジュール変更」（US1-2）
  - R5 の表の2つのテストを書き換える
  - 欠航・条件付・臨時便しか無い日・臨時便なしは今までどおり（既存のテスト）
  - 臨時便の行が抜粋で欠航（状態 `Cancelled`）なら、臨時便として数えない（「✓ 通常運航」のまま）

### Phase B：抜港あり（US2・FR-004）

- `PortBoard::extraSkipsPortsOf(int $companyId, RouteDirectionEnum $direction): bool`（R3）
- `PortBoardExtraDeparture` に `public bool $skipsPorts = false`。`routesWithExtra()` でボード全体から詰める
- `index.html.twig`：`{% if extra.skipsPorts %}・抜港あり{% endif %}`
- テスト（`PortBoardTest`。ボードを手で組む）
  - SC-004 / US2-1：10/27 下り（名瀬・本部が臨時便、亀徳・和泊・与論に同じ船の行なし）→ true
  - US2-3：9/7 上り（那覇・名瀬が臨時便、本部〜亀徳は同じ船の欠航）→ true
  - US2-2：9/27 上り（名瀬だけ）→ false。全港に寄る臨時便 → false
  - 日をまたぐ運航（今日 22:00 名瀬・明日 06:00 亀徳・明日 和泊なし・明日 10:00 与論）→ true
  - 便検索とぶつかった港（同じ船の運航予定・通常運航の行）は寄港 → false
  - 別の船の行は数えない（あいだの港に別の船の通常運航があっても true）
  - 今日を出るエントリーを含まない運航（明日だけの臨時便）は見ない → false
  - 2つの運航のどちらかに抜港 → true
- `StatusControllerTest`：会社カードの1行が「◆ 臨時便 名瀬 03:50発・抜港あり」

### Phase C：通知メールと文書（US3・FR-006・FR-010）

- `IrregularService::statusText()`：航路×日付が通常運航で港の行に Extra が1つでもあれば、頭を「スケジュール変更」にする（R4）
- テスト：`IrregularServiceCollectorTest` の「通常運航・全部 Extra」の期待を書き換え、「通常運航・Extra＋欠航」「通常運航・欠航だけ」を足す
- 12・13 の契約の該当箇所に「15-extra-voyage-badge で変更」の注記とリンク
- `make test-php`・`make phpstan`・`make cs-php`・`make lint-php`

---

## Complexity Tracking

| 増えるもの | なぜ要るか | もっと簡単な案を採らない理由 |
|---|---|---|
| 臨時便を船ごとの運航に分ける（R3） | 日をまたぐ運航・同じ日に2つの臨時便があっても、運航ごとに最初と最後の港のあいだを見る | 今日の臨時便の行を全部まとめて最初と最後を取ると、別の運航のあいだの港を抜港と取り違える |
