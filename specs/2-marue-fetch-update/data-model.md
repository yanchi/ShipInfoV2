# Data Model: マルエーフェリー情報取得方式変更

**Date**: 2026-03-08

## 概要

本機能はDBスキーマを変更しない。既存の `operation_statuses` テーブルをそのまま使用する。
変更は `MarueFerry` スクレイパークラスの内部ロジックのみ。

---

## 既存スキーマ（変更なし）

### operation_statuses

| カラム | 型 | 説明 |
|---|---|---|
| `id` | INT PK | 自動採番 |
| `route_id` | INT FK | `routes.id`（上り・下り別） |
| `status` | ENUM | `operating` / `delayed` / `cancelled` / `suspended` |
| `status_detail` | TEXT NULL | 詳細テキスト（条件付き運航の詳細等） |
| `valid_date` | DATE | 運航日付（本機能では常に `date.today()`） |
| `scraped_at` | DATETIME | スクレイプ実行日時 |
| `source_url` | VARCHAR | データ取得元URL |
| `raw_html_hash` | VARCHAR | SHA-256（重複防止用、鹿児島ページHTMLで計算） |

### routes（参照のみ）

| id | 会社 | origin_port | destination_port |
|---|---|---|---|
| 1 | マルエーフェリー | 鹿児島 | 那覇（下り） |
| 2 | マルエーフェリー | 那覇 | 鹿児島（上り） |

---

## データフロー

```
POST /search/result.php
  ↓
[便あり?]  No → route_id=1,2 両方 cancelled, valid_date=today → 保存して終了
  ↓ Yes
valid_date = date.today()  # POSTパラメータと同値、レスポンスパース不要

GET /kagoshima/
  ↓
船ごとのステータステキストを解析
  ↓
status, status_detail を取得
  ↓
route_id=1（下り）, route_id=2（上り）両方に同じ status/status_detail を適用
  ↓
raw_html_hash（鹿児島ページHTML）で重複チェック
  ↓
operation_statuses に upsert
```

---

## 中間データ構造（スクレイパー内部）

スクレイパー内部で生成する辞書のスキーマ（既存と同一）:

```python
{
    "route_id": int,            # 1（下り）or 2（上り）
    "status": OperationStatusEnum,
    "status_detail": str | None,
    "valid_date": date,         # 常に date.today()
    "scraped_at": datetime,
    "source_url": str,          # "https://www.aline-ferry.com/kagoshima/"
}
```
