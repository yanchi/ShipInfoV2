# Implementation Plan: 運航情報Webサイト

**Branch**: `master` | **Date**: 2026-03-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/website/spec.md`

---

## Summary

Symfony 7.4 + Twig で運航情報Webサイトを構築するMVP実装計画。
既存の Entity（FerryCompany / Route / OperationStatus）をそのまま活用し、
`OperationStatusRepository` にJOINクエリメソッドを2本追加、
`StatusController` に2アクション（トップページ・会社別ページ）を実装する。
DBスキーマ変更なし。Bootstrap 5をCDN経由で導入。

---

## Technical Context

**Language/Version**: PHP 8.3 + Symfony 7.4 LTS
**Primary Dependencies**: Doctrine ORM, Twig, Bootstrap 5 (CDN)
**Storage**: MySQL 8.0（既存テーブル: ferry_companies, routes, operation_statuses）
**Testing**: PHPUnit
**Target Platform**: Docker上のWebサーバー（PHP 8.3 FPM）
**Project Type**: web-service（Twig SSR）
**Performance Goals**: ページ表示 < 500ms（JOINクエリで N+1 回避）
**Constraints**: DBに当日データなしでも 500 エラー不可（SC-004）
**Scale/Scope**: フェリー会社2社・航路5〜10本のMVP

---

## Constitution Check

| 原則 | 状態 | 備考 |
|------|------|------|
| II. Webサイト優先（MVP） | ✅ PASS | Controller + Twig、API Platform不使用 |
| I. スクレイパー優先設計 | ✅ PASS | 既存DBを読み取りのみ、スクレイパー側に変更なし |
| III. データ品質保証 | ✅ PASS | 既存スキーマを変更しない |
| IV. Docker完結 | ✅ PASS | `make up` で動作、ホスト依存なし |
| V. フェーズごとのコミット | ✅ PASS | plan確定後コミット、実装後コミット予定 |

**Constitution違反: なし。** Complexity Trackingテーブル不要。

---

## Project Structure

### Documentation (this feature)

```text
specs/website/
├── spec.md              # 機能仕様
├── plan.md              # この計画書 (Phase 0-1 output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── http-routes.md   # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks コマンドで生成)
```

### Source Code

```text
app/
├── src/
│   ├── Controller/
│   │   └── StatusController.php               # 新規作成
│   ├── Repository/
│   │   └── OperationStatusRepository.php      # メソッド追加（2本）
│   └── Entity/                                # 変更なし
│       ├── FerryCompany.php
│       ├── Route.php
│       └── OperationStatus.php
└── templates/
    ├── base.html.twig                         # Bootstrap 5 CDN追加
    └── status/
        ├── index.html.twig                    # 新規作成（トップページ）
        └── company.html.twig                  # 新規作成（会社別ページ）
```

**Structure Decision**: Symfony標準のController+Twig構成。既存ディレクトリ規約に準拠。

---

## Phase 0: Research （完了）

**成果物**: [research.md](research.md)

すべての技術コンテキストが既存コードベースと spec.md から確定。NEEDS CLARIFICATIONなし。

主要な決定:
1. Bootstrap 5 CDN（Webpack Encore不使用）
2. DQL + raw SQL ハイブリッドでN+1回避（`MAX(scraped_at)` サブクエリ部分は raw SQL、Entity変換は `findBy(['id' => $ids])` バッチ取得）
3. P3（航路別ページ）はMVPスコープ外
4. ステータス表示ロジックはTwigテンプレート内

---

## Phase 1: Design & Contracts （完了）

### data-model.md

**成果物**: [data-model.md](data-model.md)

- 既存Entity（FerryCompany / Route / OperationStatus）を変更なしで使用
- DBスキーマ変更なし
- 新規追加Repositoryメソッド2本:
  - `findTodayByAllCompanies(): array` — トップページ用
  - `findRecentByCompany(FerryCompany, int): array` — 会社別ページ用
- 戻り値は `company_id`/`route_id`（int）をキーとするネスト配列（PHPのarrayはオブジェクトキー不可）
- 同一`(route_id, valid_date)`に複数レコードがある場合は `MAX(scraped_at)` サブクエリで最新1件に絞り込む

### OperationStatusEnum 表示マッピング

| Enum value | ラベル | Bootstrapクラス | アイコン |
|---|---|---|---|
| `operating` | 通常運航 | `bg-success` | ✓ |
| `delayed` | 条件付・遅延 | `bg-warning` | ● |
| `cancelled` | 欠航 | `bg-danger` | ✗ |
| `suspended` | 運休 | `bg-secondary` | - |
| `unknown` | 情報なし | `bg-secondary` | ? |

### contracts/

**成果物**: [contracts/http-routes.md](contracts/http-routes.md)

| Method | URL | Controller | Route Name |
|---|---|---|---|
| GET | `/` | `StatusController::index()` | `app_status_index` |
| GET | `/company/{id}` | `StatusController::company()` | `app_status_company` |

- 存在しないID → 404 (`createNotFoundException()`)
- FR-003: 各ページに `/company/{id}` リンク + 公式サイト（`websiteUrl`）リンクを設ける
- P3の `/route/{id}` はスコープ外

### quickstart.md

**成果物**: [quickstart.md](quickstart.md)

`make up` → `http://localhost:8080/` でトップページ確認。
`http://localhost:8080/company/{id}` で会社別ページ確認。

---

## 実装チェックリスト（tasks.md生成前サマリー）

- [x] `base.html.twig` に Bootstrap 5 CDN を追加
- [x] `OperationStatusRepository::findTodayByAllCompanies()` 実装
- [x] `OperationStatusRepository::findRecentByCompany()` 実装
- [x] `StatusController::index()` 実装（FR-003: `/company/{id}` リンク + 公式サイトリンク含む）
- [x] `StatusController::company()` 実装（404ハンドリング + FR-003: トップへ戻るリンク + 公式サイトリンク）
- [x] `templates/status/index.html.twig` 作成
- [x] `templates/status/company.html.twig` 作成
- [x] PHPUnit テスト追加（Repository・Controller）
- [x] `make test-php` グリーン確認
- [x] `http://localhost:8080/` 動作確認（SC-001〜004）
