# Feature Specification: フェリー運航情報スクレイパー

**Feature**: `scraper`
**Created**: 2026-03-07
**Status**: Draft

## 対象フェリー会社

| 会社名 | 運航状況URL | スクレイパークラス名 |
|---|---|---|
| マルエーフェリー | https://www.aline-ferry.com/status/ | MarueFerry |
| マリックスライン | https://marixline.com/service/ | MarixLine |

---

## User Scenarios & Testing

### User Story 1 - マルエーフェリーの運航状況を自動収集 (Priority: P1)

スクレイパーがマルエーフェリーの運航状況ページを定期的に取得し、DBに保存する。

**Why this priority**: 最初の実装対象。サイト構造を理解してBaseScraper実装パターンを確立する。

**Independent Test**: `make scraper-run` 実行後に `operation_statuses` テーブルにマルエーフェリーのレコードが存在すること。

**サイト構造**:
```html
<h3>フェリーあけぼの 鹿児島 - 名瀬 - 亀徳...</h3>
<h4>■3/6(金)下り便…条件付き運航</h4>
<p class="条件付運航">条件付運航</p>
<p>詳細な理由テキスト...</p>
```

クラス名と状態のマッピング:
- `通常運航` → `operating`
- `条件付運航` → `delayed`（条件付き）
- `欠航` → `cancelled`
- `スケジュール変更` / `運航遅延` → `delayed`

**Acceptance Scenarios**:

1. **Given** マルエーフェリーのサイトが正常な場合、**When** スクレイパーを実行、**Then** 各便の運航状況が `operation_statuses` テーブルに保存される
2. **Given** 同じHTMLを2回スクレイピング、**When** `raw_html_hash` が一致、**Then** 重複レコードは作成されない
3. **Given** サイトが503を返す場合、**When** スクレイパーを実行、**Then** リトライ（最大3回）後に `scraper_logs` にエラーが記録される

---

### User Story 2 - マリックスラインの運航状況を自動収集 (Priority: P2)

スクレイパーがマリックスラインの運航状況ページを定期的に取得し、DBに保存する。

**Why this priority**: マルエーフェリーと異なるHTML構造（クラスベース）への対応。

**Independent Test**: `make scraper-run` 実行後に `operation_statuses` テーブルにマリックスラインのレコードが存在すること。

**サイト構造**:
```html
<div class="status_single normal">
  <div class="info1">
    <span class="date">3/7（金）</span>
    <span class="exp">通常運航</span>
  </div>
</div>
<div class="status_single alert">
  <div class="info1">
    <span class="date">3/8（土）</span>
    <span class="exp">欠航</span>
  </div>
</div>
```

CSSクラスと状態のマッピング:
- `.status_single.normal` → `operating`
- `.status_single.alert` → `cancelled` または `delayed`（`.exp` テキストで判定）

**Acceptance Scenarios**:

1. **Given** マリックスラインのサイトが正常な場合、**When** スクレイパーを実行、**Then** 各便の運航状況が保存される
2. **Given** `.status_single.alert` の便、**When** `.exp` が「欠航」、**Then** status が `cancelled` で保存される

---

### User Story 3 - 定期実行スケジューリング (Priority: P3)

スクレイパーが30分間隔で自動的に全社のスクレイピングを実行する。

**Why this priority**: データ鮮度の維持。単発実行が動いてから対応。

**Independent Test**: Dockerコンテナが起動後30分以上経過した時点で `scraper_logs` に複数の成功ログがあること。

**Acceptance Scenarios**:

1. **Given** scraperコンテナが起動、**When** 30分経過、**Then** 自動的に全社のスクレイピングが実行される
2. **Given** スクレイピングが失敗、**When** 次の30分サイクル、**Then** 自動的に再試行される

---

### Edge Cases

- HTML構造が変更された場合: `scraper_logs` にパース失敗を記録し、他社のスクレイピングは継続する
- ネットワークタイムアウト: tenacityで最大3回リトライ（指数バックオフ）
- 日付解析の失敗: ログに警告を残してそのレコードをスキップ
- `ferry_companies` テーブルに登録されていない会社: `SCRAPER_REGISTRY` に存在しない場合はスキップ

---

## Requirements

### Functional Requirements

- **FR-001**: System MUST スクレイパー実行開始・終了時に `scraper_logs` テーブルにレコードを記録すること
- **FR-002**: System MUST `raw_html_hash`（SHA-256）で重複スクレイピングを防止すること
- **FR-003**: System MUST 1社のスクレイピング失敗が他社の処理をブロックしないこと
- **FR-004**: System MUST HTTPリクエストにリトライロジック（最大3回、指数バックオフ）を実装すること
- **FR-005**: System MUST `--once` フラグで1回だけ実行できること（`make scraper-run` 用）
- **FR-006**: System MUST 環境変数 `SCRAPER_INTERVAL_MINUTES` でスクレイピング間隔を設定できること

### Key Entities

- **FerryCompany**: スクレイパークラス名（`scraper_class`）を持つ
- **Route**: 航路（出発港・到着港・会社への紐づき）
- **OperationStatus**: 運航状況の各レコード（`valid_date` + `route_id` がキー）
- **ScraperLog**: 実行ログ（成功・失敗・処理件数）

### 航路マスタデータ（初期投入）

| 会社 | 航路名 | 出発港 | 到着港 |
|---|---|---|---|
| マルエーフェリー | 鹿児島〜名瀬〜亀徳 | 鹿児島 | 亀徳 |
| マルエーフェリー | 鹿児島〜名瀬 | 鹿児島 | 名瀬 |
| マリックスライン | 鹿児島〜那覇 | 鹿児島 | 那覇 |

※スクレイピング時にサイトの表記から航路を特定し `route_id` にマッピングする

---

## Success Criteria

- **SC-001**: `make scraper-run` 実行後、5分以内に両社のレコードが `operation_statuses` に保存される
- **SC-002**: 同じデータを2回スクレイピングしても `operation_statuses` の件数が増えない（重複防止）
- **SC-003**: `scraper_logs` で実行履歴・エラー内容が確認できる
- **SC-004**: 1社のサイトがダウンしても、もう1社のスクレイピングは正常完了する
