# ShipInfoV2 Constitution

## Core Principles

### I. スクレイパー優先設計
フェリー会社のウェブサイトから運航情報を収集することが本システムの起点。
スクレイパー（Python）はサイト変更に対して堅牢であること。
各フェリー会社は独立したスクレイパークラスとして実装し、`BaseScraper`を継承すること。
スクレイパーの追加・削除がシステム全体に影響を与えないよう疎結合に設計すること。

### II. Webサイト優先（MVP）
MVPではREST APIを提供せず、Twigテンプレートを用いたWebサイトとして運航情報を提供する。
API Platformは使用しない。Symfonyの標準的なController + Twigの構成とすること。
スクレイパーはDBに直接書き込む設計とする。
REST APIの提供はMVP以降のフェーズで検討する。

### III. データ品質保証
`raw_html_hash`（SHA-256）による重複スクレイピング防止を必須とする。
運航状況の変更履歴はすべて`operation_statuses`テーブルに保持すること。
スクレイパーの実行ログは`scraper_logs`テーブルに記録し、障害追跡を可能にする。

### IV. Docker完結
ローカル開発環境はDockerで完全に動作すること。
ホストマシンへの依存（PHPインストール、Pythonインストール等）を持たないこと。
`make init`一発で開発環境が起動できる状態を維持すること。

### V. フェーズごとのコミット（NON-NEGOTIABLE）
実装は必ずフェーズ単位でコミットすること。
- 仕様確定後にコミット
- 実装計画確定後にコミット
- 各タスクグループ完了後にコミット
AIの暴走を防ぐため、一度に実装するスコープを明確に制限すること。

## 技術スタック制約

### 使用技術（変更禁止）
- **スクレイパー**: Python 3.12 + BeautifulSoup4 + SQLAlchemy
- **Webアプリ（MVP）**: PHP 8.3 + Symfony 7.4 (LTS) + Twig（API Platformは使用しない）
- **データベース**: MySQL 8.0
- **ローカル環境**: Docker Compose

### コーディング規約
- PHPはPSR-12準拠、Symfony規約に従うこと
- Pythonはblack + ruffでフォーマット・リントを行うこと
- テストはPHPUnit（PHP）とpytest（Python）を使用すること

## 開発ワークフロー

### SDDフロー
1. `/speckit.specify` で機能仕様を作成
2. `/speckit.plan` で実装計画を作成
3. `/speckit.tasks` でタスクを分解
4. `/speckit.implement` でタスクを実行
5. 各フェーズ完了後にgit commit

### ディレクトリ規約
- `specs/<feature-name>/` に仕様・計画・タスクを配置
- スクレイパー実装は `scraper/scraper/scrapers/<company_name>.py`
- Symfony Entityは `app/src/Entity/`
- APIリソース設定はEntityのAttributeで管理（YAMLファイル不使用）

## Governance

本Constitutionはすべての開発判断に優先する。
変更には明文化された理由が必要。
技術的負債は即日解消することを原則とする。

**Version**: 1.1.0 | **Ratified**: 2026-03-07 | **Last Amended**: 2026-03-07
