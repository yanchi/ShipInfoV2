# Implementation Plan: no_service ステータス追加

**Branch**: `3-no-service-status` | **Date**: 2026-03-08 | **Spec**: [spec.md](spec.md)

---

## Summary

`OperationStatusEnum` に `no_service`（当日便なし）を追加し、「欠航」と「便無し」を区別する。
Python モデル・PHP Enum・マルエーフェリー・マリックスライン 2社のスクレイパーを更新。
DB スキーマ変更なし（`status` カラムは既に VARCHAR(255)）。

---

## Technical Context

**Language/Version**: Python 3.12 / PHP 8.3
**Primary Dependencies**: SQLAlchemy, BeautifulSoup4, Symfony 7.4
**Storage**: MySQL 8.0（`operation_statuses.status` は VARCHAR(255)）
**Testing**: pytest（Python）/ PHPUnit（PHP）
**Project Type**: Scraper + Web application（MVP）
**DB Migration**: 不要（VARCHAR(255) のためマイグレーション不要）
**Constraints**: `BaseScraper.fetch()` / `parse()` シグネチャ変更禁止

---

## Constitution Check

| Gate | Status | 備考 |
|---|---|---|
| スクレイパーは BaseScraper 継承 | ✅ PASS | 既存クラスを修正するだけ |
| スクレイパーは MySQL に直接書き込む | ✅ PASS | 変更なし |
| Docker 完結 | ✅ PASS | DB マイグレーション不要 |
| フェーズ単位コミット | ✅ PASS | tasks.md で管理 |
| REST API 不使用（MVP） | ✅ PASS | スクレイパー・Enum のみ変更 |

---

## Project Structure

### Documentation

```
specs/3-no-service-status/
├── spec.md
├── research.md
├── data-model.md
├── plan.md          ← このファイル
├── quickstart.md
└── tasks.md         （/speckit.tasks で生成）
```

### 変更対象ファイル

```
scraper/scraper/db/models.py                  # OperationStatusEnum に no_service 追加
app/src/Enum/OperationStatusEnum.php           # NoService ケース追加
scraper/scraper/scrapers/marue_ferry.py        # no-service パスのステータス変更
scraper/scraper/scrapers/marix_line.py         # parse 後 no_service 追加ロジック
scraper/tests/test_marue_ferry.py              # no-service アサーション更新
scraper/tests/test_marix_line.py               # モック修正 + no_service テスト追加
```

---

## Phase 0: Research 結果

→ [research.md](research.md) 参照。

**主要決定事項**:
- DB マイグレーション不要（VARCHAR(255) で `no_service` 文字列をそのまま保存）
- MarixLine: parse 後に `seen` セットを参照し、今日のレコードがないルートへ `no_service` を追加
- MarueFerry: no-service パスの `cancelled` を `no_service` に変更するだけ

---

## Phase 1: 実装設計

### Step 1: OperationStatusEnum 拡張（Python）

`scraper/scraper/db/models.py` の `OperationStatusEnum` に `no_service = "no_service"` を追加。

### Step 2: OperationStatusEnum 拡張（PHP）

`app/src/Enum/OperationStatusEnum.php` に `case NoService = 'no_service';` を追加。

### Step 3: MarueFerry no-service パス変更

`scraper/scraper/scrapers/marue_ferry.py` の `parse()` メソッド:

```python
# 変更前
"status": OperationStatusEnum.cancelled,
# 変更後
"status": OperationStatusEnum.no_service,
```

コメントも「cancelled → no_service」に更新する。

### Step 4: MarixLine no-service 追加ロジック

`scraper/scraper/scrapers/marix_line.py` の `parse()` メソッドの末尾（既存ループの後）に追加:

```python
# 本日便のないルートに no_service を記録
today = date.today()
for route in [r for r in [down_route, up_route] if r]:
    if (route.id, today) not in seen:
        records.append({
            "route_id": route.id,
            "status": OperationStatusEnum.no_service,
            "status_detail": None,
            "valid_date": today,
            "scraped_at": datetime.now(),
            "source_url": SOURCE_URL,
        })
```

### Step 5: テスト更新（MarueFerry）

`scraper/tests/test_marue_ferry.py`:
- `test_no_service_records_cancelled_for_both_routes` → テスト名・アサーションを `no_service` に変更

### Step 6: テスト更新・追加（MarixLine）

`scraper/tests/test_marix_line.py`:

**既存テストの修正**:
- `date.today()` を `unittest.mock.patch` で HTML 内の日付（`date(2026, 3, 7)` 等）に固定する
- `len(records)` のアサーションが変わらないように確認

**新規テスト**:
- `test_no_service_when_no_block_for_today`: 今日の便ブロックなし → both routes に `no_service` が記録される
- `test_no_service_only_for_missing_route`: 下りのみブロックあり（今日）→ 上りのみ `no_service`

---

## 実装順序

```
T001: Python OperationStatusEnum に no_service 追加
T002: PHP OperationStatusEnum に NoService 追加
T003: MarueFerry no-service パス変更 (cancelled → no_service)
T004: MarueFerry テスト更新
T005: MarixLine no_service 追加ロジック実装
T006: MarixLine 既存テスト修正（date.today() モック）
T007: MarixLine no_service テスト追加
T008: 全テスト実行確認 (make test-scraper)
```

---

## リスク・注意点

| リスク | 対策 |
|---|---|
| MarixLine の既存テストが date.today() に依存して壊れる | unittest.mock.patch で today を HTML 内日付にモック |
| PHP側 で no_service を参照している箇所が他にある | `grep -r "OperationStatusEnum"` で確認（現 MVP は StatusController のみ） |
| make migrate-diff が予期しない migration を生成 | 実行して確認（何も変化なければ OK）。VARCHAR(255) のまま |
