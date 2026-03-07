# Quickstart: マルエーフェリー情報取得方式変更

## 開発環境セットアップ

```bash
make up          # Docker起動
make migrate     # DBマイグレーション（スキーマ変更なし、念のため）
```

## 実装ファイル

変更対象ファイル:

```
scraper/scraper/scrapers/marue_ferry.py   # 実装（主要変更）
scraper/tests/test_marue_ferry.py         # テスト（追加・更新）
```

## 動作確認

```bash
# スクレイパーを1回実行（マルエーフェリーも含む全社）
make scraper-run

# マルエーフェリーのみ確認したい場合はシェル接続して手動実行
make shell-scraper
# コンテナ内で make scraper-run か、scraper CLI の使い方に従って
# マルエーフェリー向けスクレイパーのみを実行してください。
```

## デバッグ

検索エンドポイントのレスポンスを確認する場合:

```bash
make shell-scraper
python -c "
import requests
from datetime import date
resp = requests.post(
    'https://www.aline-ferry.com/search/result.php',
    data={'startDate': date.today().strftime('%Y-%m-%d'), 'startPort': '50', 'endPort': '83'},
    timeout=30
)
print(resp.status_code)
print(resp.text[:3000])
"
```

鹿児島航路ページの確認:

```bash
python -c "
import requests
resp = requests.get('https://www.aline-ferry.com/kagoshima/', timeout=30)
resp.encoding = resp.apparent_encoding
print(resp.text[:3000])
"
```

## テスト実行

```bash
make test-scraper
```

## 確認クエリ（MySQL）

```sql
-- マルエーフェリーの最新レコード確認
SELECT os.*, r.origin_port, r.destination_port
FROM operation_statuses os
JOIN routes r ON os.route_id = r.id
JOIN ferry_companies fc ON r.ferry_company_id = fc.id
WHERE fc.name = 'マルエーフェリー'
ORDER BY os.scraped_at DESC
LIMIT 10;
```

## 注意事項

- 検索エンドポイントのPOSTパラメータ名（`startDate`, `startPort`, `endPort`）は実際のフォームと一致している前提。初回実行時にレスポンスが意図通りか確認すること。
- 鹿児島ページのHTML構造はWordPressテーマ更新で変わる可能性あり。パーサーがスキップした場合は warning ログを確認。
