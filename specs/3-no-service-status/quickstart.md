# Quickstart: no_service ステータス追加

## 開発環境セットアップ

```bash
make up          # Docker起動
```

DB マイグレーションは不要（status カラムは既に VARCHAR(255)）。

## 変更対象ファイル

```
# 実装
scraper/scraper/db/models.py               # Python Enum
app/src/Enum/OperationStatusEnum.php        # PHP Enum
scraper/scraper/scrapers/marue_ferry.py     # MarueFerry
scraper/scraper/scrapers/marix_line.py      # MarixLine

# テスト
scraper/tests/test_marue_ferry.py
scraper/tests/test_marix_line.py
```

## 動作確認

```bash
make test-scraper    # pytestでスクレイパーテスト全件
make scraper-run     # 実際にスクレイパーを実行（本日便なし日に実行すると no_service が記録される）
```

## 確認クエリ

```sql
-- no_service が正しく記録されているか確認
SELECT route_id, status, valid_date, status_detail
FROM operation_statuses
WHERE status = 'no_service'
ORDER BY scraped_at DESC
LIMIT 10;
```
