<!--
Sync Impact Report
- Version change: 2.0.0 → 2.1.0（MINOR：ディレクトリ規約で、会社のスクレイパーをパッケージにしてよいとした）
- Modified principles: なし
- Modified sections: 開発ワークフロー > ディレクトリ規約（スクレイパー実装の置き場所）
- Added sections: なし
- Removed sections: なし
- Templates:
  - ✅ .specify/templates/plan-template.md（ディレクトリ規約を参照していないので変更なし）
  - ✅ .specify/templates/spec-template.md（変更なし）
  - ✅ .specify/templates/tasks-template.md（変更なし）
- Dependent artifacts:
  - ✅ CLAUDE.md（スクレイパー追加手順）
  - ✅ README.md（スクレイパー追加手順）
  - ✅ specs/17-scraper-refactor/plan.md（Constitution Check・Complexity Tracking・Phase E）
  - ⚠ AGENTS.md（CLAUDE.md から作り直す。リポジトリには入っていない）
- Follow-up TODOs: なし
- 理由: specs/17-scraper-refactor（marue_ferry.py が 1788 行になり、役割ごとに分けるため）
-->

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
運航状況はキーごとの最新状態を1行で保持し、内容が変わったら同じ行を上書きすること。
- `operation_statuses`：航路 × 日付ごとに1行
- `departure_statuses`：航路 × 港 × 出港日 × 船ごとに1行

変更の履歴（同じキーの過去の状態）は MVP では保持しない。
理由：MVP には履歴を使う画面・機能が無い。履歴を持つなら保持期間も設計する必要があり、
使い道が無いまま貯めると負債になる。履歴が必要な機能を作るときは、保持期間とあわせて
追記型の履歴テーブルを設計すること。
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
  - 1ファイルが大きくなり役割ごとに分けるときは、`scraper/scraper/scrapers/<company_name>/` のパッケージにしてよい。
    import の名前（`scraper.scrapers.<company_name>`）と `SCRAPER_REGISTRY` に登録するクラスは変えないこと。
    パッケージの中も、その会社のコードだけを置く（会社をまたいで使うものは `BaseScraper` か `scraper/scraper/utils/`）
- Symfony Entityは `app/src/Entity/`
- APIリソース設定はEntityのAttributeで管理（YAMLファイル不使用）

## Governance

本Constitutionはすべての開発判断に優先する。
変更には明文化された理由が必要。
技術的負債は即日解消することを原則とする。

**Version**: 2.1.0 | **Ratified**: 2026-03-07 | **Last Amended**: 2026-11-02
