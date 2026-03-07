# ShipInfoV2 - Claude Code Development Guide

## プロジェクト概要

フェリー会社の運航情報を収集・管理・提供するシステム。

- **スクレイパー**: Python（`scraper/`）
- **Webアプリ（MVP）**: PHP Symfony 7.4 LTS + Twig（`app/`）
- **データベース**: MySQL 8.0
- **ローカル環境**: Docker Compose

## 開発原則（必読）

プロジェクト憲法: [.specify/memory/constitution.md](.specify/memory/constitution.md)

すべての開発判断はConstitutionに従うこと。

## Spec-Driven Development (SDD) ワークフロー

新機能開発は必ず以下のフローで行うこと:

```
/speckit.specify  →  /speckit.plan  →  /speckit.tasks  →  /speckit.implement
```

各フェーズ完了後に `git commit` すること（NON-NEGOTIABLE）。

## よく使うコマンド

```bash
make up            # Docker起動
make down          # Docker停止
make migrate       # DBマイグレーション実行
make shell-php     # PHPコンテナにシェル接続
make shell-scraper # Scraperコンテナにシェル接続
make test-php      # PHPUnitテスト
make test-scraper  # pytestテスト
make scraper-run   # スクレイパー即時実行
```

## ディレクトリ構造

```
ShipInfoV2/
├── app/                      # Symfony 7.4アプリ
│   └── src/
│       ├── Entity/           # Doctrineエンティティ
│       ├── Enum/             # PHPバックドEnum
│       └── Repository/       # Doctrineリポジトリ
├── scraper/                  # Pythonスクレイパー
│   └── scraper/
│       ├── scrapers/         # 会社別スクレイパー（BaseScraper継承）
│       ├── db/               # SQLAlchemyモデル・接続
│       └── utils/            # 共通ユーティリティ
├── docker/                   # Dockerビルドコンテキスト
├── specs/                    # 機能仕様（SDD成果物）
└── .specify/                 # SpecKitテンプレート・メモリ
```

## スクレイパー追加手順

1. `scraper/scraper/scrapers/<company_name>.py` を作成（`BaseScraper`継承）
2. `scraper/scraper/scrapers/__init__.py` の `SCRAPER_REGISTRY` に登録
3. DBの `ferry_companies` テーブルに会社レコードを追加（`scraper_class` カラムにクラス名）

## 重要な設計決定

- MVPはTwig + ControllerによるWebサイト（API Platformは使用しない）
- スクレイパーはMySQLに直接書き込む（Symfonyを経由しない）
- `raw_html_hash` で重複スクレイピングを防止
- phpmyadminは `make up-tools` でのみ起動（デフォルト除外）
- REST APIはMVP以降のフェーズで検討
