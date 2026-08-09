# Data Model — トップページ会社カード横並びグリッド

**Feature**: `1-company-card-grid` | **Date**: 2026-03-08

---

## 結論: データモデル変更なし

本機能は **プレゼンテーション層（Twig テンプレート）のみの変更** であり、以下はすべて変更しない。

| 対象 | 変更 |
|---|---|
| Doctrine Entity（`FerryCompany` / `Route` / `OperationStatus` / `ScraperLog`） | なし |
| DB スキーマ・マイグレーション | なし |
| `OperationStatusEnum` / `ScraperStatusEnum` | なし |
| Repository のクエリ | なし |
| Controller が Twig に渡す変数の形 | なし |
| スクレイパー（Python 側） | なし |

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
