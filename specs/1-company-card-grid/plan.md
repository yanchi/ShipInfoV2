# Implementation Plan: トップページ会社カード横並びグリッドレイアウト

**Branch**: `1-company-card-grid` | **Date**: 2026-03-08 | **Spec**: [spec.md](spec.md)

---

## Summary

トップページ（[index.html.twig](../../app/templates/status/index.html.twig)）の会社カードを縦積みから
レスポンシブ横並びグリッドに変更し、表示順による視覚的な優劣感をなくす。

Bootstrap 5 の `row-cols-*` ユーティリティのみで実装する。カスタムCSS・新規ファイル・
DB変更・Controller変更はいずれも不要で、**変更するのは Twig 1ファイルとテスト1ファイルのみ**。

> **訂正（PR #16 レビュー）**: グリッド化そのものは上記のとおり Twig だけで完結した。ただし実装中に見つかった既存不具合を同じ PR で直したので、
> 実際の変更範囲は次のとおり広い（詳細は [tasks.md](tasks.md) の「実装中に判明した事項」と [data-model.md](data-model.md) を参照）。
>
> - `app/src/Repository/OperationStatusRepository.php`: INNER JOIN → LEFT JOIN（航路0件の会社が消える問題）
> - `app/src/Entity/OperationStatus.php`: `#[ORM\HasLifecycleCallbacks]` の追加（PrePersist が呼ばれない問題）
> - `app/src/DataFixtures/AppFixtures.php`: 空のスタブを、実データを投入する実装に置き換え
> - `docker/mysql/init/02_seed.sql`: `created_at` / `updated_at` の明示指定（seed が失敗する問題）
> - `app/tests/Repository/OperationStatusRepositoryTest.php`: 回帰テストを追加
>
> DB スキーマ・マイグレーション・Controller・スクレイパーは変更していない。

---

## Technical Context

**Language/Version**: PHP 8.3
**Primary Dependencies**: Symfony 7.4 LTS, Twig, Bootstrap 5.3.3（CDN、[base.html.twig](../../app/templates/base.html.twig) で読み込み済み）
**Storage**: 変更なし（MySQL 8.0 / 読み取りのみ）
**Testing**: PHPUnit（`WebTestCase` による DOM セレクタ検証）+ ブラウザでの手動レスポンシブ確認
**Target Platform**: モダンブラウザ（デスクトップ / タブレット / スマートフォン）
**Project Type**: Web application（MVP・Twig）
**DB Migration**: 不要
**Constraints**:
- カード内部コンテンツ（`card-header` 以下）は一切変更しない（FR-005）
- 0件時の alert 表示は既存動作を維持する（FR-006）
- 新規CSSアセットを追加しない（[research.md](research.md) R-001）

---

## Constitution Check

*GATE: Phase 0 前に通過必須。Phase 1 設計後に再評価。*

| Gate | Status | 備考 |
|---|---|---|
| I. スクレイパー優先設計 | ✅ PASS | スクレイパーに影響なし（`scraper/` 配下は無変更） |
| II. Webサイト優先（MVP）／API Platform不使用 | ✅ PASS | Twig テンプレートのみの変更。API は追加しない |
| III. データ品質保証 | ✅ PASS | `raw_html_hash`・`operation_statuses`・`scraper_logs` に影響なし |
| IV. Docker完結 | ✅ PASS | ホスト依存の追加なし。ビルドツール・アセットパイプライン不要 |
| V. フェーズごとのコミット（NON-NEGOTIABLE） | ✅ PASS | spec / plan / 実装の各フェーズでコミット |
| 技術スタック制約（PHP 8.3 + Symfony 7.4 + Twig） | ✅ PASS | 既存スタック内で完結。依存追加ゼロ |
| コーディング規約（PSR-12 / Symfony規約） | ✅ PASS | PHP 変更はテストのみ、PSR-12 準拠で記述 |

**Post-Design 再評価（Phase 1 完了後）**: 違反なし。設計により変更ファイルが2つに収まり、
Constitution の「技術的負債は即日解消」の観点でも新規負債を生まない。

---

## Project Structure

### Documentation (this feature)

```text
specs/1-company-card-grid/
├── spec.md              # 機能仕様（/speckit.specify 出力・plan フェーズで BP と高さ方針を更新）
├── checklists/
│   └── requirements.md  # 仕様品質チェックリスト（決定事項を追記）
├── research.md          # Phase 0 出力
├── data-model.md        # Phase 1 出力（変更なしを明記）
├── quickstart.md        # Phase 1 出力（検証手順）
├── plan.md              # このファイル
└── tasks.md             # Phase 2 出力（/speckit.tasks で生成・未作成）
```

`contracts/` は作成しない。本機能は外部インターフェース（API・CLI・スキーマ）を一切公開せず、
既存 HTML ページの内部レイアウト変更に閉じているため。

### Source Code (repository root)

```text
app/
├── templates/
│   └── status/
│       └── index.html.twig          # ★変更: グリッドラッパー追加
└── tests/
    └── Controller/
        └── StatusControllerTest.php # ★変更: グリッド構造テスト4件追加
```

**Structure Decision**: 既存の Symfony 標準構成（`app/templates/` + `app/tests/`）をそのまま使う。
本機能はプレゼンテーション層のみの変更のため、`app/src/` 配下・`scraper/` 配下・`app/migrations/` は
1ファイルも触らない。

> **訂正（PR #16 レビュー）**: グリッド化では `app/src/` を触っていないが、既存不具合の修正で `app/src/`（Repository / Entity / DataFixtures）と
> `docker/mysql/init/02_seed.sql` を変更した（上記 Summary の訂正を参照）。`scraper/` と `app/migrations/` は変更していない。

---

## Phase 0: Research 結果

→ [research.md](research.md) 参照。

**主要決定事項**:

| ID | 決定 |
|---|---|
| R-001 | Bootstrap `row-cols-*` ユーティリティで実装。カスタムCSSは書かない |
| R-002 | ブレークポイントは Bootstrap 標準の `md`=768px / `lg`=992px（spec の 600/900 から変更） |
| R-003 | カードに `h-100` を付け、同一行内で高さを揃える（spec の「自然な高さ」から変更） |
| R-004 | 変更はループ外の `row` 追加と `.col` ラッパー追加に閉じる。カード内部は不変 |
| R-005 | PHPUnit で DOM 構造を検証、実際の折り返しは quickstart の手動確認でカバー |

R-002・R-003 は spec の記述と食い違うため、[spec.md](spec.md) の FR-002〜FR-004・Edge Cases・
Success Criteria と [checklists/requirements.md](checklists/requirements.md) を決定内容に合わせて更新済み。

---

## Phase 1: 実装設計

### Step 1: グリッドラッパーの追加（[index.html.twig](../../app/templates/status/index.html.twig)）

`{% else %}`（= `companies` が空でない側）の直下に `row` を開き、`{% endfor %}` の直後に閉じる。

```twig
{% else %}
    <div class="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-4">
        {% for companyData in companies %}
            ...
        {% endfor %}
    </div>
{% endif %}
```

`{% if companies is empty %}` の alert は `row` の外側に残るため、FR-006 は自動的に満たされる。

### Step 2: 各カードを `.col` で包み、クラスを差し替える

```twig
{# 変更前 #}
<div class="card mb-4">

{# 変更後 #}
<div class="col">
    <div class="card h-100">
```

- `mb-4` を **削除**: 行間は `row` の `g-4` ガターが担当する。残すと行間が二重に空く（R-004）。
- `h-100` を **追加**: `.col` の高さいっぱいまでカードを伸ばし、同一行の高さを揃える（R-003 / SC-004）。
- 対応する `</div>` の閉じタグを1つ追加する（インデントも1段深くする）。

### Step 3: カード内部は変更しない

`card-header`（会社名リンク・公式サイトリンク）、`list-group`（航路名・ステータスバッジ6種・
`航路情報がありません。`）はすべて現状維持。FR-005 のデグレード防止要件。

### Step 4: 機能テストの追加（[StatusControllerTest.php](../../app/tests/Controller/StatusControllerTest.php)）

既存4テストは変更せず、以下3件を追加する。

> **訂正（PR #16 レビュー）**: 最終的には4件追加した（下表の4行目）。また、テスト用データを作るために `setUp` で client を共有する形にしたので、
> 既存4テストも `static::createClient()` → `$this->client` に書き換えている（アサーションは変えていない）。

| テストメソッド | アサーション |
|---|---|
| `testIndexRendersCompanyGrid` | `.row.row-cols-1.row-cols-md-2.row-cols-lg-3` が存在 |
| `testCompanyCardsAreGridColumns` | `.row > .col > .card.h-100` が存在 |
| `testIndexKeepsCardContent` | `.card .card-header` と `.card .list-group` が存在（FR-005 のデグレード検知） |
| `testIndexShowsNoRouteMessageForCompanyWithoutRoutes` | 航路0件の会社のカードに `航路情報がありません。` が表示される（spec Edge Cases）※レビュー対応で追加 |

> **注意**: テスト DB に会社データが無い場合、カード自体が描画されない。
> ~~データ有無に依存しない書き方（0件なら `markTestSkipped`）にする。~~
> **訂正（PR #16 レビュー）**: skip 方式だと、空のテスト DB では検証が一度も走らないまま green になる。
> 各テストで必要な会社データを作成し、tearDown で削除する方式に変更した。

### Step 5: 動作確認

```bash
make test-php    # 自動テスト
make up          # ブラウザで 375 / 800 / 1200px を目視確認
```

詳細手順は [quickstart.md](quickstart.md) 参照。

---

## 実装順序

```
T001: index.html.twig にグリッドラッパー（row）を追加
T002: 各カードを .col で包み、mb-4 削除 / h-100 追加
T003: StatusControllerTest にグリッド構造テストを追加
T004: make test-php で全テスト green を確認
T005: ブラウザで 375 / 800 / 1200px のレスポンシブ目視確認（quickstart.md）
```

タスクの正式な分解は `/speckit.tasks` で [tasks.md](tasks.md) を生成する。

---

## リスク・注意点

| リスク | 対策 |
|---|---|
| `mb-4` の削除漏れで行間が二重に空く | quickstart のチェックリストに明記。目視確認項目に含める |
| `</div>` の閉じタグ追加漏れで HTML が壊れる | `make test-php` の `assertResponseIsSuccessful` と DOM セレクタテストで検知 |
| テスト DB が空でグリッドテストが常に skip される | テスト内で会社データを作成・削除し、DB の状態に依存しないようにする（`make fixtures` は dev DB にしか投入されないので対策にならない） |
| カード内部を巻き込んで変更してしまう（FR-005 違反） | 差分をラッパー部分に限定。`testIndexKeepsCardContent` で検知 |
| 会社1社のみのときカードが横に伸びきる | `row-cols-*` は列幅を固定するため発生しない（1/3幅で左寄せ）。quickstart で確認 |

---

## Complexity Tracking

Constitution Check に違反なし。記載事項なし。
