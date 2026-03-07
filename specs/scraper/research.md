# Research: フェリー運航情報スクレイパー

**Feature**: `scraper` | **Date**: 2026-03-07

---

## Decision 1: HTMLパーサー

- **Decision**: BeautifulSoup4 + lxml バックエンド
- **Rationale**: BeautifulSoup4 は壊れたHTMLへの耐性が高く、フェリー会社サイトの不完全なHTMLを安定してパースできる。lxml は純粋な html.parser より高速。
- **Alternatives considered**: scrapy（重すぎる）、lxml 単体（BS4のAPIの方が直感的）

## Decision 2: スケジューラ

- **Decision**: `schedule` ライブラリ（シンプルな cron 風 DSL）
- **Rationale**: 常駐 Python プロセスが単純な定期実行をするだけ。Celery/APScheduler は過剰。
- **Alternatives considered**: APScheduler（機能過剰）、cron（Dockerコンテナとの相性が悪い）

## Decision 3: HTTPリトライ

- **Decision**: `requests` + `urllib3.util.Retry`（backoff_factor=1.0、最大3回）
- **Rationale**: requests ネイティブのリトライ機構を使うことで tenacity などの追加依存を最小化できる。503/429 に対してバックオフリトライを適用。
- **Alternatives considered**: tenacity（柔軟だが over-engineering）

## Decision 4: ORM / DB アクセス

- **Decision**: SQLAlchemy 2.0（Session ベース、`sessionmaker` + コンテキストマネージャ）
- **Rationale**: Symfony 側（MySQL 8.0）と同じスキーマを参照するため ORM が必要。SQLAlchemy は Python における事実上の標準。
- **Alternatives considered**: peewee（軽量だが移植性低）、生SQL（型安全性なし）

## Decision 5: ロギング

- **Decision**: `structlog`（構造化ログ、JSON出力可）
- **Rationale**: Docker 環境では JSON 形式の構造化ログが Fluentd/CloudWatch との連携に有利。`scraper_class` や `company_id` をコンテキストとしてバインドできる。
- **Alternatives considered**: Python 標準 logging（構造化が難しい）

## Decision 6: 方向判定ロジック

- **MarueFerry**: h4 テキストの「下り便」/「上り便」キーワードで判定。方向不明（「通常運航致しております。」等）→ 両方向に同じデータを適用。片方のみ記録がある日付はもう一方を `operating` で自動補完。
- **MarixLine**: `div.info2` 内の出発港テキスト（`鹿児島X発` → 下り、`那覇X発` → 上り）で判定。
- **Rationale**: 各社のサイト構造を実際に確認した上で、最も壊れにくいパターンを選択。

## Decision 7: 重複防止

- **Decision**: `raw_html_hash`（SHA-256）でページ全体のハッシュを計算し、既存レコードと比較。ハッシュが同じなら upsert をスキップ。
- **Rationale**: ステータスが変わらなければ不要な UPDATE を避けられる。ページ単位のハッシュなので計算コストが低い。
- **Alternatives considered**: レコード単位の diff（複雑すぎる）
