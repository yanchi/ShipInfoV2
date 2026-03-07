# Implementation Plan: フェリー運航情報スクレイパー

**Branch**: `master` | **Date**: 2026-03-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/scraper/spec.md`

## Summary

フェリー会社2社（マルエーフェリー・マリックスライン）の運航状況ページをスクレイピングし、MySQL DB へ保存する Python 常駐プロセス。`BaseScraper` 抽象クラスを継承した会社別クラスで実装し、30分間隔でスケジュール実行する。

## Technical Context

**Language/Version**: Python 3.11+ (Docker: 3.12-slim)
**Primary Dependencies**: BeautifulSoup4 + lxml, SQLAlchemy 2.0, requests + urllib3 Retry, schedule, structlog
**Storage**: MySQL 8.0（Docker）/ SQLite in-memory（テスト用）
**Testing**: pytest + responses（HTTPモック）
**Target Platform**: Docker コンテナ（Linux、常駐プロセス）
**Project Type**: background scraper / daemon
**Performance Goals**: 全フェリー会社のスクレイピングを30分以内に完了
**Constraints**: タイムアウト30秒/リクエスト、HTTPリトライ最大3回（backoff_factor=1.0）
**Scale/Scope**: 2社（初期）、スクレイパー追加を疎結合で対応

## Constitution Check

| Gate | 結果 | 備考 |
|---|---|---|
| I. スクレイパー優先設計 — BaseScraper継承、疎結合 | ✓ PASS | SCRAPER_REGISTRY で動的解決 |
| II. DBに直接書き込み、API Platform不使用 | ✓ PASS | Symfony 側は読み取り専用 |
| III. raw_html_hash + scraper_logs 実装 | ✓ PASS | SHA-256、全実行をログ記録 |
| IV. Docker完結 | ✓ PASS | docker/python/Dockerfile 実装済み |
| V. フェーズごとのコミット | ⚠ 後付け | 既存実装のため例外。次フィーチャーから遵守 |

## Project Structure

### Documentation (this feature)

```text
specs/scraper/
├── spec.md          # 機能仕様
├── plan.md          # 本ファイル
├── research.md      # 技術決定の根拠
├── data-model.md    # エンティティ定義
├── quickstart.md    # 開発・運用手順
└── tasks.md         # タスクリスト（/speckit.tasks 出力）
```

### Source Code

```text
scraper/
├── pyproject.toml               # パッケージ定義
├── requirements.txt             # 本番依存
├── requirements-dev.txt         # 開発依存（pytest, responses, ruff等）
├── scraper/                     # Pythonパッケージ
│   ├── __init__.py
│   ├── main.py                  # エントリーポイント（schedule ループ）
│   ├── config.py                # 環境変数設定
│   ├── db/
│   │   ├── connection.py        # get_session() コンテキストマネージャ
│   │   └── models.py            # SQLAlchemy ORM モデル
│   ├── scrapers/
│   │   ├── __init__.py          # SCRAPER_REGISTRY + get_all_scrapers()
│   │   ├── base.py              # BaseScraper（fetch/parse/run/_upsert）
│   │   ├── marue_ferry.py       # MarueFerry 実装
│   │   └── marix_line.py        # MarixLine 実装
│   └── utils/
│       └── http.py              # create_session()（リトライ付き requests）
└── tests/
    ├── conftest.py              # db_session / company fixtures
    ├── test_base_upsert.py      # BaseScraper._upsert DB動作テスト
    ├── test_marue_ferry.py      # MarueFerry ユニットテスト
    └── test_marix_line.py       # MarixLine ユニットテスト
```

**Structure Decision**: Single project（スクレイパー単体）。外部 API 公開なし、contracts/ 不要。

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| なし | — | — |
