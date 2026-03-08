# Data Model: no_service ステータス追加

**Branch**: `3-no-service-status`
**Date**: 2026-03-08

---

## 変更対象

### OperationStatusEnum（Python）

```python
# scraper/scraper/db/models.py
class OperationStatusEnum(str, enum.Enum):
    operating  = "operating"
    cancelled  = "cancelled"
    delayed    = "delayed"
    suspended  = "suspended"
    unknown    = "unknown"
    no_service = "no_service"   # ← 追加
```

### OperationStatusEnum（PHP）

```php
// app/src/Enum/OperationStatusEnum.php
enum OperationStatusEnum: string {
    case Operating = 'operating';
    case Cancelled = 'cancelled';
    case Delayed   = 'delayed';
    case Suspended = 'suspended';
    case Unknown   = 'unknown';
    case NoService = 'no_service';   // ← 追加
}
```

---

## スキーマ変更なし

`operation_statuses.status` は `VARCHAR(255)` のため、DB マイグレーション不要。

---

## ステータス値の意味整理

| 値 | 意味 |
|---|---|
| `operating` | 通常運航 |
| `cancelled` | 欠航（便は設定されていたが中止） |
| `delayed` | 遅延・条件付き運航 |
| `suspended` | 運休（長期または通達ベース） |
| `unknown` | 判定不能 |
| `no_service` | 当日便なし（そもそも便が設定されていない日） |
