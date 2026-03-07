# Tasks: フェリー運航情報スクレイパー

**Feature**: `scraper` | **Date**: 2026-03-07 | **Plan**: [plan.md](plan.md)

**Total Tasks**: 16 | **Completed**: 16 | **Remaining**: 0

---

## Dependencies

```
Phase 1 (Setup) → Phase 2 (Foundational) → Phase 3 (US1) → Phase 4 (US2) → Phase 5 (US3) → Final
Phase 3 and Phase 4 can run in parallel after Phase 2.
```

## Parallel Execution

- Phase 2: T005, T006 は並列実行可（互いに依存なし）
- Phase 3: T009, T010 は並列実行可（同ファイルではない）
- Phase 4: T011, T012 は並列実行可（同ファイルではない）

---

## Phase 1: Setup — プロジェクト初期化

- [X] T001 scraper/ パッケージディレクトリ構造を作成する（scraper/, scraper/db/, scraper/scrapers/, scraper/utils/, scraper/tests/）
- [X] T002 依存パッケージ定義を作成する (scraper/requirements.txt, scraper/requirements-dev.txt)
- [X] T003 パッケージメタデータを作成する (scraper/pyproject.toml)

---

## Phase 2: Foundational — 基盤実装（全 US の前提）

- [X] T004 SQLAlchemy ORM モデルを実装する (scraper/scraper/db/models.py) — FerryCompany, Route, OperationStatus, ScraperLog + Enum
- [X] T005 [P] DB 接続モジュールを実装する (scraper/scraper/db/connection.py) — get_session() コンテキストマネージャ
- [X] T006 [P] HTTP ユーティリティを実装する (scraper/scraper/utils/http.py) — urllib3 Retry 付き create_session()
- [X] T007 設定モジュールを実装する (scraper/scraper/config.py) — DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD, SCRAPER_INTERVAL_MINUTES, LOG_LEVEL
- [X] T008 BaseScraper 抽象クラスを実装する (scraper/scraper/scrapers/base.py) — fetch/parse/run/_upsert + ScraperLog 記録
- [X] T009 pytest フィクスチャを作成する (scraper/tests/conftest.py) — db_session, marue_ferry_company, marix_line_company

---

## Phase 3: US1 — マルエーフェリーの運航状況を自動収集

**Story Goal**: スクレイパーがマルエーフェリーの運航状況ページを取得し DB に保存する
**Independent Test**: `pytest tests/test_marue_ferry.py` が全件パスすること

- [X] T010 [P] [US1] MarueFerry スクレイパーを実装する (scraper/scraper/scrapers/marue_ferry.py) — h4 パース、方向判定、片方補完ロジック
- [X] T011 [P] [US1] MarueFerry ユニットテストを作成する (scraper/tests/test_marue_ferry.py) — 5テストケース（条件付・欠航・補完・detail・重複防止）

---

## Phase 4: US2 — マリックスラインの運航状況を自動収集

**Story Goal**: スクレイパーがマリックスラインの運航状況ページを取得し DB に保存する
**Independent Test**: `pytest tests/test_marix_line.py` が全件パスすること

- [X] T012 [P] [US2] MarixLine スクレイパーを実装する (scraper/scraper/scrapers/marix_line.py) — CSS クラス判定、info2 日付パース、方向判定
- [X] T013 [P] [US2] MarixLine ユニットテストを作成する (scraper/tests/test_marix_line.py) — 5テストケース（通常/条件付・欠航・無関係div除外・日付パース）

---

## Phase 5: US3 — 定期実行スケジューリング

**Story Goal**: スクレイパーが 30 分間隔で全社のスクレイピングを自動実行する
**Independent Test**: Docker コンテナ起動後に scraper_logs に複数の成功ログが記録されること

- [X] T014 [US3] スクレイパーレジストリを実装する (scraper/scraper/scrapers/__init__.py) — SCRAPER_REGISTRY, get_all_scrapers()
- [X] T015 [US3] メインエントリーポイントを実装する (scraper/scraper/main.py) — schedule ループ、--once フラグ、structlog 設定

---

## Final Phase: Polish & Cross-Cutting

- [X] T016 全テストの通過を確認する — `pytest tests/ -v` 14/14 PASSED

---

## Implementation Strategy

**MVP scope**: Phase 1〜3（US1 完了）でデータが DB に蓄積され始める
**Incremental**: US2 追加で2社対応、US3 追加で常駐化
**実装済み**: 全 16 タスク完了（2026-03-07）
