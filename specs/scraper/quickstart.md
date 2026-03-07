# Quickstart: フェリー運航情報スクレイパー

**Feature**: `scraper` | **Date**: 2026-03-07

---

## ローカル開発環境のセットアップ

```bash
# 1. 仮想環境作成・依存インストール
cd scraper
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pip install -e .

# 2. テスト実行（DB不要・モックHTTP）
.venv/bin/pytest tests/ -v
```

---

## Docker での実行

```bash
# 初回セットアップ
make init

# スクレイパーを1回だけ手動実行
make scraper-run

# ログ確認
docker compose logs scraper
```

---

## 新しいスクレイパーの追加

1. `scraper/scraper/scrapers/<company>.py` を作成し `BaseScraper` を継承
2. `fetch()` と `parse()` を実装
3. `scraper/scraper/scrapers/__init__.py` の `SCRAPER_REGISTRY` に登録
4. `ferry_companies` テーブルに `scraper_class` を登録（Docker init SQL または migration）

```python
# scraper/scraper/scrapers/my_company.py
from scraper.scrapers.base import BaseScraper

SOURCE_URL = "https://example.com/status/"

class MyCompany(BaseScraper):
    def fetch(self) -> str:
        resp = self.http.get(SOURCE_URL, timeout=30)
        resp.raise_for_status()
        return resp.text

    def parse(self, html: str) -> list[dict]:
        # ... 解析ロジック
        return records
```

---

## Integration Scenarios

### Scenario 1: 通常運航の収集

```
1. make scraper-run
2. SELECT * FROM operation_statuses WHERE status = 'operating';
   → 両社の便が保存されている
```

### Scenario 2: 重複防止の確認

```
1. make scraper-run  # 1回目
2. make scraper-run  # 2回目（同じHTML）
3. SELECT COUNT(*) FROM operation_statuses;
   → 件数が増えていない
```

### Scenario 3: エラーログ確認

```
1. （ネットワーク断の状態で）make scraper-run
2. SELECT * FROM scraper_logs WHERE status = 'failed';
   → error_message に例外内容が記録されている
```

---

## 環境変数

| 変数名 | デフォルト | 説明 |
|---|---|---|
| `DB_HOST` | `localhost` | MySQLホスト |
| `DB_PORT` | `3306` | MySQLポート |
| `DB_NAME` | `shipinfo` | データベース名 |
| `DB_USER` | — | MySQLユーザー名（必須） |
| `DB_PASSWORD` | — | MySQLパスワード（必須） |
| `SCRAPER_INTERVAL_MINUTES` | `30` | スクレイピング間隔（分） |
| `LOG_LEVEL` | `INFO` | ログレベル |
