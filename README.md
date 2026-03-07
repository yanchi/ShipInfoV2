# ShipInfoV2

フェリー会社の運航情報を収集・表示するWebサービス。

- **スクレイパー**: 各社公式サイトから運航状況を定期収集（Python）
- **Webサイト**: 当日の運航状況・直近3日分の履歴を表示（PHP Symfony + Twig）

## システム構成

```
scraper/    Python スクレイパー（cron で定期実行）
app/        Symfony 7.4 Webアプリ
docker/     Docker Compose 設定
specs/      機能仕様（Spec-Driven Development）
```

## セットアップ

### 必要なもの

- Docker / Docker Compose

### 初回セットアップ

```bash
cp .env.example .env          # 環境変数を設定
cp scraper/.env.example scraper/.env

make init   # ビルド・起動・マイグレーション一括実行
```

ブラウザで http://localhost:8080 を開く。

## 主要コマンド

```bash
make up            # Docker 起動
make down          # Docker 停止
make migrate       # DB マイグレーション実行
make fixtures      # テストデータ投入
make scraper-run   # スクレイパー即時実行
make test-php      # PHPUnit テスト
make test-scraper  # pytest テスト
make shell-php     # PHP コンテナにシェル接続
make shell-scraper # Scraper コンテナにシェル接続
make up-tools      # phpMyAdmin も起動（http://localhost:8081）
```

## スクレイパーの追加

1. `scraper/scraper/scrapers/<company>.py` を作成（`BaseScraper` 継承）
2. `scraper/scraper/scrapers/__init__.py` の `SCRAPER_REGISTRY` に登録
3. DB の `ferry_companies` テーブルに会社レコードを追加

## 技術スタック

| 役割 | 技術 |
|------|------|
| Web フレームワーク | PHP 8.3 + Symfony 7.4 LTS |
| テンプレート | Twig + Bootstrap 5 |
| ORM | Doctrine ORM |
| スクレイパー | Python 3.x |
| DB | MySQL 8.0 |
| インフラ | Docker Compose |
