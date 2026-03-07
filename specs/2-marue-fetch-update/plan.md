# Implementation Plan: マルエーフェリー情報取得方式変更

**Branch**: `2-marue-fetch-update` | **Date**: 2026-03-08 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/2-marue-fetch-update/spec.md`

## Summary

マルエーフェリーの運航情報取得を、`/status/` ページのh3/h4解析から2ステップ方式に変更する。
まず検索エンドポイントへのPOSTで本日便の有無・日付を確認し、便がある場合は鹿児島航路ページから各船のステータスを取得して上り・下り両方のルートに適用する。

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: requests + urllib3（HTTP）, BeautifulSoup4 + lxml（HTML解析）, SQLAlchemy（DB）
**Storage**: MySQL 8.0（既存スキーマ、変更なし）
**Testing**: pytest
**Target Platform**: Linux（Docker コンテナ）
**Project Type**: バックグラウンドスクレイパーサービス（単一クラス変更）
**Performance Goals**: スクレイプ完了まで5分以内
**Constraints**: `BaseScraper` 継承維持、既存DBスキーマ変更なし、`raw_html_hash` 重複防止維持
**Scale/Scope**: `MarueFerry` クラス1ファイルの変更のみ

## Constitution Check

| 原則 | ステータス | 備考 |
|---|---|---|
| I. スクレイパー優先設計 | ✅ PASS | `BaseScraper` 継承維持、疎結合変更なし |
| II. Webサイト優先（MVP） | ✅ N/A | スクレイパーのみ。WebアプリへのAPI追加なし |
| III. データ品質保証 | ✅ PASS | `raw_html_hash`・`scraper_logs` 維持 |
| IV. Docker完結 | ✅ PASS | Dockerfileの変更なし |
| V. フェーズごとのコミット | ✅ PLAN | 仕様確定コミット済み。実装完了後に再コミット予定 |

Constitution 違反なし。Phase 1 設計に進む。

## Project Structure

### Documentation (this feature)

```text
specs/2-marue-fetch-update/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (変更対象)

```text
scraper/
└── scraper/
    └── scrapers/
        └── marue_ferry.py   # MarueFerry クラスを全面書き換え（fetch/parse メソッド）
```

変更なし（参照のみ）:
```text
scraper/scraper/scrapers/base.py     # BaseScraper（継承元、変更なし）
scraper/scraper/db/models.py         # OperationStatusEnum・Route（変更なし）
```

## Implementation Approach

### Step 1: 検索エンドポイントPOST（運航有無確認）

- **URL**: `https://www.aline-ferry.com/search/result.php`
- **Method**: POST
- **Parameters**: `startDate=YYYY-MM-DD`（当日）, `startPort=50`, `endPort=83`
- **判定**: `table.s-result tbody tr` が1行以上あれば「運航あり」、なければ「運航なし」
- **`valid_date`**: `date.today()`（POSTパラメータの `startDate` と同値。レスポンスHTMLのパース不要）
- **注意**: 結果の「会社名」がマリックスラインでも「便あり」と判定する（共同運航のため）
- **便なし時**: 上り・下り両ルートを `cancelled` で記録して処理終了

### Step 2: 鹿児島航路ページ解析（ステータス詳細取得）

- **URL**: `https://www.aline-ferry.com/kagoshima/`
- **Method**: GET
- **構造**: 船ごとに `<a>` ブロック（`div.ferry-name`: 船名、`div.tag-list > span`: ステータス、`div.situation-excerpt`: 詳細テキスト）
- **ステータスマッピング**:
  - `通常運航` → `operating`
  - `条件付` → `delayed`
  - `欠航` → `cancelled`
  - `運休` → `suspended`
  - `遅延` / `スケジュール変更` → `delayed`
- **方向**: 上り・下り両方のルートに同じステータスを適用
- **当日分なし**: warning ログを記録してスキップ（保存しない）

### Step 3: DB保存

- 既存の `BaseScraper.save()` / `upsert` ロジックを踏襲
- `raw_html_hash`: 鹿児島ページの HTML の SHA-256
- `valid_date`: Step 1 で取得した日付（または today フォールバック）
- 重複キー `(route_id, valid_date)` は既存ロジックで防止
