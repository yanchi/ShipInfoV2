# Data Model: フェリー運航情報スクレイパー

**Feature**: `scraper` | **Date**: 2026-03-07

---

## Entities

### FerryCompany

フェリー会社マスタ。スクレイパークラス名を保持し、`SCRAPER_REGISTRY` との紐付けに使用する。

| フィールド | 型 | 制約 | 説明 |
|---|---|---|---|
| id | Integer | PK, AUTO_INCREMENT | |
| name | String(255) | NOT NULL, UNIQUE | 会社名（例: マルエーフェリー） |
| website_url | String(512) | NULLABLE | 公式サイトURL |
| scraper_class | String(255) | NULLABLE | スクレイパークラス名（例: MarueFerry） |
| active | Boolean | NOT NULL, DEFAULT TRUE | 有効フラグ |
| created_at | DateTime | NOT NULL | |
| updated_at | DateTime | NOT NULL | |

---

### Route

航路マスタ。会社ごとに上り・下りで2レコード。

| フィールド | 型 | 制約 | 説明 |
|---|---|---|---|
| id | Integer | PK, AUTO_INCREMENT | |
| ferry_company_id | Integer | FK(ferry_companies.id), NOT NULL | |
| name | String(255) | NOT NULL | 航路名（例: 鹿児島〜那覇（下り）） |
| origin_port | String(255) | NOT NULL | 出発港（鹿児島 / 那覇） |
| destination_port | String(255) | NOT NULL | 到着港（那覇 / 鹿児島） |
| active | Boolean | NOT NULL, DEFAULT TRUE | |
| created_at | DateTime | NOT NULL | |
| updated_at | DateTime | NOT NULL | |

**方向判定**: `origin_port == "鹿児島"` → 下り、`origin_port == "那覇"` → 上り

**初期マスタデータ**:

| id | 会社 | origin_port | destination_port |
|---|---|---|---|
| 1 | マルエーフェリー | 鹿児島 | 那覇 |
| 2 | マルエーフェリー | 那覇 | 鹿児島 |
| 3 | マリックスライン | 鹿児島 | 那覇 |
| 4 | マリックスライン | 那覇 | 鹿児島 |

---

### OperationStatus

運航状況レコード。`route_id + valid_date` がユニークキー（upsert 対象）。

| フィールド | 型 | 制約 | 説明 |
|---|---|---|---|
| id | BigInteger | PK, AUTO_INCREMENT | |
| route_id | Integer | FK(routes.id), NOT NULL | |
| status | Enum | NOT NULL, DEFAULT unknown | operating / cancelled / delayed / suspended / unknown |
| status_detail | Text | NULLABLE | 詳細テキスト（欠航理由等） |
| valid_date | Date | NOT NULL | 対象日付 |
| departure_time | DateTime | NULLABLE | 出発時刻（未実装、将来用） |
| arrival_time | DateTime | NULLABLE | 到着時刻（未実装、将来用） |
| scraped_at | DateTime | NOT NULL | スクレイピング実行時刻 |
| source_url | String(512) | NULLABLE | スクレイピング元URL |
| raw_html_hash | String(64) | NULLABLE | SHA-256ハッシュ（重複防止） |
| created_at | DateTime | NOT NULL | |
| updated_at | DateTime | NOT NULL | |

**INDEX**: `(route_id, valid_date)` UNIQUE（upsert 判定に使用）

**OperationStatusEnum**:
- `operating` — 通常運航
- `cancelled` — 欠航
- `delayed` — 条件付き/遅延
- `suspended` — 運休
- `unknown` — 不明

---

### ScraperLog

スクレイパー実行ログ。1実行 = 1レコード。

| フィールド | 型 | 制約 | 説明 |
|---|---|---|---|
| id | BigInteger | PK, AUTO_INCREMENT | |
| ferry_company_id | Integer | FK(ferry_companies.id), NOT NULL | |
| started_at | DateTime | NOT NULL | |
| finished_at | DateTime | NULLABLE | |
| status | Enum | NOT NULL, DEFAULT running | running / success / failed |
| records_created | Integer | NOT NULL, DEFAULT 0 | 新規作成件数 |
| records_updated | Integer | NOT NULL, DEFAULT 0 | 更新件数 |
| error_message | Text | NULLABLE | エラー内容 |
| created_at | DateTime | NOT NULL | |
| updated_at | DateTime | NOT NULL | |

**ScraperStatusEnum**: `running` / `success` / `failed`

---

## Relationships

```
FerryCompany 1──n Route 1──n OperationStatus
FerryCompany 1──n ScraperLog
```

## State Transitions (OperationStatus)

```
なし（新規） → operating | cancelled | delayed | suspended
既存レコード → raw_html_hash 変化時のみ更新
```
