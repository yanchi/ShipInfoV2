# Data Model: 運航情報Webサイト

**Phase**: 1 (Design)
**Feature**: website
**Date**: 2026-03-07

---

## 既存エンティティ（変更なし）

本featureではDBスキーマ変更・新規Entityは不要。すべて既存Entityを読み取り専用で使用。

---

## Entity 関係図

```
FerryCompany (ferry_companies)
    │  id, name, websiteUrl, scraperClass, active
    │
    │ 1:N
    ▼
Route (routes)
    │  id, ferryCompany_id, name, originPort, destinationPort, active
    │
    │ 1:N
    ▼
OperationStatus (operation_statuses)
       id, route_id, status(Enum), statusDetail, validDate,
       departureTime, arrivalTime, scrapedAt, sourceUrl, rawHtmlHash, createdAt
```

---

## 各Entityの詳細

### FerryCompany

| フィールド | 型 | 説明 |
|---|---|---|
| id | int unsigned | PK |
| name | string(255) | 会社名（例: マルエーフェリー） |
| websiteUrl | string(512) \| null | 公式サイトURL（リンク表示用） |
| scraperClass | string(255) \| null | スクレイパークラス名 |
| active | bool | 有効フラグ |
| createdAt | datetime | |
| updatedAt | datetime | |

**WebサイトMVPでの用途**: トップページと会社別ページで `name` と `websiteUrl` を表示。

### Route

| フィールド | 型 | 説明 |
|---|---|---|
| id | int unsigned | PK |
| ferryCompany | FK → FerryCompany | |
| name | string(255) | 航路名（例: 鹿児島〜名瀬〜亀徳） |
| originPort | string(255) \| null | 出発港 |
| destinationPort | string(255) \| null | 到着港 |
| active | bool | 有効フラグ |
| createdAt | datetime | |
| updatedAt | datetime | |

**WebサイトMVPでの用途**: 会社ごとの航路一覧表示。`active = true` のもののみ表示。

### OperationStatus

| フィールド | 型 | 説明 |
|---|---|---|
| id | bigint unsigned | PK |
| route | FK → Route | |
| status | OperationStatusEnum | 運航ステータス |
| statusDetail | text \| null | 詳細メッセージ（欠航理由など） |
| validDate | date | この状況が適用される日付 |
| departureTime | datetime \| null | 出発時刻 |
| arrivalTime | datetime \| null | 到着時刻 |
| scrapedAt | datetime | スクレイピング時刻 |
| sourceUrl | string(512) \| null | スクレイピング元URL |
| rawHtmlHash | string(64) \| null | SHA-256（重複防止用） |
| createdAt | datetime | |

**WebサイトMVPでの用途**: `validDate` と `status` を主要表示項目として使用。

### OperationStatusEnum

| value | ラベル | 表示色 | アイコン |
|---|---|---|---|
| `operating` | 通常運航 | 緑 (`success`) | ✓ |
| `delayed` | 条件付・遅延 | 黄 (`warning`) | ● |
| `cancelled` | 欠航 | 赤 (`danger`) | ✗ |
| `suspended` | 運休 | グレー (`secondary`) | - |
| `unknown` | 情報なし | グレー (`secondary`) | ? |

---

## 必要なRepositoryメソッド（新規追加）

### OperationStatusRepository

#### `findTodayByAllCompanies(): array`

トップページ用。本日の全社・全航路の最新ステータスを返す。

```
戻り値構造（company_id をキーにネスト）:
[
    $companyId => [
        'company' => FerryCompany,
        'routes'  => [
            $routeId => [
                'route'  => Route,
                'status' => OperationStatus|null,
            ],
            ...
        ],
    ],
    ...
]
```

> **注意**: PHPのarrayはオブジェクトをキーにできないため、`company_id` / `route_id`（int）をキーとする。

**実装方針**:
1. `active = true` の FerryCompany・Route を JOIN して取得
2. `valid_date = TODAY` の OperationStatus を LEFT JOIN
3. 同一 `(route_id, valid_date)` に複数レコードが存在しうるため（スクレイパー複数回実行）、**サブクエリで `MAX(scraped_at)` を絞り込んで最新1件を取得**
4. PHP側で `company_id → route_id → OperationStatus|null` のネスト構造に整形

```sql
-- 最新レコード取得の方針（raw SQL で実装）
-- ※ DQLでは MAX(scraped_at) サブクエリの表現が困難なため raw SQL を使用
INNER JOIN (
    SELECT route_id, MAX(scraped_at) AS latest_scraped_at
    FROM operation_statuses
    WHERE valid_date = ?
    GROUP BY route_id
) latest ON os.route_id = latest.route_id
        AND os.scraped_at = latest.latest_scraped_at
```

#### `findRecentByCompany(FerryCompany $company, int $days = 3): array`

会社別ページ用。直近N日分のステータスを日付×航路で返す。

```
戻り値構造（date文字列 → route_id のネスト）:
[
    '2026-03-07' => [
        $routeId => ['route' => Route, 'status' => OperationStatus|null],
        ...
    ],
    '2026-03-06' => [...],
    '2026-03-05' => [...],
]
```

> **注意**: 日付キーは `'Y-m-d'` 形式の文字列（Twigで表示しやすいため）。

**実装方針**:
1. `valid_date >= (TODAY - N days)` の OperationStatus を取得
2. 各 `(route_id, valid_date)` で `MAX(scraped_at)` による最新1件に絞り込み
3. PHP側で日付→route_id→エンティティのネスト構造に整形（日付は降順）

---

## DBスキーマ変更

**なし。** 既存テーブルの読み取りのみ。
