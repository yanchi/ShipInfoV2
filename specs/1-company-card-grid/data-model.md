# Data Model — トップページ会社カード横並びグリッド

**Feature**: `1-company-card-grid` | **Date**: 2026-03-08

---

## 結論: データモデル変更なし

グリッド化そのものは **プレゼンテーション層（Twig テンプレート）だけの変更**。DB スキーマとビューモデルの形は変えない。

ただし作業中に見つかった既存不具合を同じ PR で直したので、Entity と Repository にも実装上の変更がある（下表の「既存不具合の修正」）。

| 対象 | 変更 |
|---|---|
| DB スキーマ・マイグレーション | なし |
| `OperationStatusEnum` / `ScraperStatusEnum` | なし |
| Controller が Twig に渡す変数の形 | なし |
| スクレイパー（Python 側） | なし |
| `OperationStatus` Entity | **既存不具合の修正**: `#[ORM\HasLifecycleCallbacks]` を追加した。この属性がなかったため `#[ORM\PrePersist]` の `onPrePersist()` が呼ばれず、Doctrine 経由（fixtures 等）で保存すると `created_at` が NULL になって NOT NULL 違反で失敗していた |
| `OperationStatusRepository::findTodayByAllCompanies()` | **既存不具合の修正**: `INNER JOIN` を `LEFT JOIN ... WITH r.active = :active` に変更した。有効な航路を持たない会社が結果から消え、「航路情報がありません。」の分岐に到達できなかったため。戻り値の形は変わらない（その会社の `routes` が空配列になるだけ） |
| `docker/mysql/init/02_seed.sql` | **既存不具合の修正**: `created_at` / `updated_at` に値を明示的に入れるようにした（現行スキーマにはこの2カラムの DEFAULT がないため） |

---

## 既存のビューモデル（変更なし・参照用）

[StatusController::index()](../../app/src/Controller/StatusController.php) が `status/index.html.twig` に渡す構造。本機能ではこの形をそのまま使う。

```
companies: array               # OperationStatusRepository::findTodayByAllCompanies() の戻り値
  └─ companyData
       ├─ company: FerryCompany
       │    ├─ id: int
       │    ├─ name: string
       │    └─ websiteUrl: ?string
       └─ routes: array
            └─ routeData
                 ├─ route: Route
                 │    └─ name: string
                 └─ status: ?OperationStatus
                      └─ status: OperationStatusEnum   # operating / delayed / cancelled
                                                       # / suspended / no_service / unknown

today: DateTimeImmutable        # 表示日付（'today'）
```

### 描画上の分岐（変更なし）

| 条件 | 表示 |
|---|---|
| `companies` が空 | `現在情報がありません。`（alert） |
| `companyData.routes` が空 | `航路情報がありません。`（list-group-item） |
| `routeData.status` が `null` | `情報なし` バッジ |
| `status.status.value` の各値 | 対応するステータスバッジ（6種） |

これらの分岐ロジックは FR-005・FR-006 により **1つも変更しない**。グリッド化はこの分岐より外側のラッパー要素にのみ適用する。

---

## DOM 構造の変更（プレゼンテーションのみ）

### 変更前

```
div.container
└─ (for companyData in companies)
     └─ div.card.mb-4          ← 縦積み
          ├─ div.card-header
          └─ ul.list-group
```

### 変更後

```
div.container
└─ div.row.row-cols-1.row-cols-md-2.row-cols-lg-3.g-4    ← 新規ラッパー
     └─ (for companyData in companies)
          └─ div.col                                      ← 新規ラッパー
               └─ div.card.h-100                          ← mb-4 削除 / h-100 追加
                    ├─ div.card-header                    ← 中身は不変
                    └─ ul.list-group                      ← 中身は不変
```

`{% if companies is empty %}` の alert 分岐は `row` の外側に置き、0件時にグリッドを描画しない。
