# Feature Specification: フェリー運航情報スクレイパー

**Feature**: `scraper`
**Created**: 2026-03-07
**Status**: Implemented（2-marue-fetch-update / 3-no-service-status の変更を反映済み）

## 対象フェリー会社

| 会社名 | 運航状況URL | スクレイパークラス名 |
|---|---|---|
| マルエーフェリー | https://www.aline-ferry.com/search/result.php（便有無）<br>https://www.aline-ferry.com/kagoshima/（詳細ステータス） | MarueFerry |
| マリックスライン | https://marixline.com/service/ | MarixLine |

---

## User Scenarios & Testing

### User Story 1 - マルエーフェリーの運航状況を自動収集 (Priority: P1)

スクレイパーがマルエーフェリーの運航状況ページを定期的に取得し、DBに保存する。

**Why this priority**: 最初の実装対象。サイト構造を理解してBaseScraper実装パターンを確立する。

**Independent Test**: `make scraper-run` 実行後に `operation_statuses` テーブルにマルエーフェリーのレコードが存在すること。

> **取得方式**: 当初は `/status/` ページの h3/h4 解析方式だったが、[2-marue-fetch-update](../2-marue-fetch-update/spec.md) で2ステップ方式に変更済み。便なし日の扱いは [3-no-service-status](../3-no-service-status/spec.md) を参照。

**取得フロー**（実サイト確認済み 2026-03-08）:

1. **Step 1 — 本日便の有無確認**: `POST https://www.aline-ferry.com/search/result.php`（`startDate=今日, startPort=50, endPort=83`）
   - `table.s-result tbody tr` が1行以上 → 便あり → Step 2 へ
   - 0行 → 便なし → 上り・下り両航路を `no_service`（`status_detail = null`）で記録して終了
   - `table.s-result` 自体がない → サイト構造変更とみなし warning を出して「便あり」（安全側）で Step 2 へ
2. **Step 2 — 詳細ステータス取得**: `GET https://www.aline-ferry.com/kagoshima/`

```html
<a href="...">
  <div class="route-head">
    <div class="ferry-name">フェリーあけぼの</div>
    <div class="route-detail">鹿児島 - 名瀬 - ...</div>
  </div>
  <div class="tag-list">
    <span class="tag-normal">通常運航</span>
  </div>
  <div class="situation-excerpt">通常運航致しております。</div>
</a>
```

ステータス判定（`div.tag-list span` のテキストから）:
- `欠航` → `cancelled`
- `条件付` → `delayed`
- `遅延` / `スケジュール変更` → `delayed`
- `運休` → `suspended`
- `通常` → `operating`

その他のルール:
- 複数船のステータスが混在する場合は最も深刻なものを採用（`cancelled` > `suspended` > `delayed` > `operating`）し、warning を記録
- 採用したステータスを上り・下り両航路に適用
- `status_detail` は `div.situation-excerpt` のテキスト（`operating` の場合は `null`）
- `valid_date` は常に `date.today()`（POST の `startDate` と同値）
- `raw_html_hash` は鹿児島ページの HTML で計算（便なし時は空文字列のハッシュ）
- 船ブロックを1件も解析できない場合はサイト構造変更とみなし例外 → `scraper_logs` に `failed`

**Acceptance Scenarios**:

1. **Given** マルエーフェリーのサイトが正常な場合、**When** スクレイパーを実行、**Then** 各便の運航状況が `operation_statuses` テーブルに保存される
2. **Given** 検索エンドポイントで本日便が0件、**When** スクレイパーを実行、**Then** 上り・下り両航路が `no_service` で保存される
3. **Given** 同じHTMLを2回スクレイピング、**When** `raw_html_hash` が一致、**Then** 重複レコードは作成されない
4. **Given** サイトが503を返す場合、**When** スクレイパーを実行、**Then** リトライ（最大3回）後に `scraper_logs` にエラーが記録される

---

### User Story 2 - マリックスラインの運航状況を自動収集 (Priority: P2)

スクレイパーがマリックスラインの運航状況ページを定期的に取得し、DBに保存する。

**Why this priority**: マルエーフェリーと異なるHTML構造（クラスベース）への対応。

**Independent Test**: `make scraper-run` 実行後に `operation_statuses` テーブルにマリックスラインのレコードが存在すること。

**サイト構造**（実サイト確認済み 2026-03-07）:
```html
<!-- 通常運航 -->
<div class="status_single_cover normal">
  <a class="status_single normal" href="https://marixline.com/service/downstream20260307/">
    <div class="info1">
      <p class="exp">通常運航</p>
    </div>
    <div class="info2">
      2026年3月7日 鹿児島新港発 2026年3月8日 那覇港 向け
    </div>
  </a>
</div>

<!-- 条件付運航 -->
<div class="status_single_cover conditional alert">
  <a class="status_single conditional alert" href="...">
    <div class="info1">
      <p class="exp">条件付運航</p>
    </div>
    <div class="info2">
      2026年3月7日 那覇港発 2026年3月8日 鹿児島新港 向け
    </div>
  </a>
</div>
```

CSSクラスと状態のマッピング（`div.status_single_cover` のクラスで判定）:
- `normal` → `operating`
- `conditional` + `alert` → `delayed`（条件付き）
- `alert`（`conditional` なし）→ `cancelled`（欠航）

日付: `div.info2` 内の最初の `YYYY年M月D日` パターンを `valid_date` として使用

本日便がない航路の扱い（[3-no-service-status](../3-no-service-status/spec.md)）:
- HTML 内に「本日日付 + その航路の出発港発」のブロックがない → `no_service`（`status_detail = null`）
- ブロックはあるのに解析できなかった → パース不具合の可能性として warning を出し `unknown`

**Acceptance Scenarios**:

1. **Given** マリックスラインのサイトが正常な場合、**When** スクレイパーを実行、**Then** 各便の運航状況が保存される
2. **Given** `.status_single.alert` の便、**When** `.exp` が「欠航」、**Then** status が `cancelled` で保存される
3. **Given** 本日出発の便がない航路、**When** スクレイパーを実行、**Then** その航路が `no_service` で保存される

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

- HTML構造が変更された場合: パーサーログ（warning/debug）を残し、致命的例外時は `scraper_logs` を `failed` で記録。他社のスクレイピングは継続する
- ネットワークタイムアウト/5xx: `requests + urllib3 Retry` により最大3回リトライ（backoff_factor=1.0）
- 日付解析の失敗:
  - MarixLine: warning ログを残してそのレコードをスキップ
  - MarueFerry: 日付は解析せず常に `valid_date = today` を使用
- `ferry_companies` テーブルに登録されていない会社: `SCRAPER_REGISTRY` に存在しない場合はスキップ

---

## Requirements

### Functional Requirements

- **FR-001**: System MUST スクレイパー実行開始・終了時に `scraper_logs` テーブルにレコードを記録すること
- **FR-002**: System MUST `raw_html_hash`（SHA-256）で重複スクレイピングを防止すること
- **FR-003**: System MUST 1社のスクレイピング失敗が他社の処理をブロックしないこと
- **FR-004**: System MUST HTTPリクエストにリトライロジック（`requests + urllib3 Retry`、最大3回、backoff_factor=1.0）を実装すること
- **FR-005**: System MUST `--once` フラグで1回だけ実行できること（`make scraper-run` 用）
- **FR-006**: System MUST 環境変数 `SCRAPER_INTERVAL_MINUTES` でスクレイピング間隔を設定できること

### Key Entities

- **FerryCompany**: スクレイパークラス名（`scraper_class`）を持つ
- **Route**: 航路（出発港・到着港・会社への紐づき）
- **OperationStatus**: 運航状況の各レコード（`valid_date` + `route_id` がキー）
- **ScraperLog**: 実行ログ（成功・失敗・処理件数）

### 航路マスタデータ（初期投入）

| id | 会社 | 航路名 | 出発港 | 到着港 | 方向 |
|---|---|---|---|---|---|
| 1 | マルエーフェリー | 鹿児島〜那覇（下り） | 鹿児島 | 那覇 | 下り |
| 2 | マルエーフェリー | 那覇〜鹿児島（上り） | 那覇 | 鹿児島 | 上り |
| 3 | マリックスライン | 鹿児島〜那覇（下り） | 鹿児島 | 那覇 | 下り |
| 4 | マリックスライン | 那覇〜鹿児島（上り） | 那覇 | 鹿児島 | 上り |

方向の判定ロジック:
- **マルエーフェリー**: 方向別には判定しない。鹿児島航路ページで採用したステータスを上り・下り両方に適用
- **マリックスライン**: div.info2 の「鹿児島X発」→ 下り、「那覇X発」→ 上り

※ `origin_port` カラムで上り・下りを区別（鹿児島発 = 下り、那覇発 = 上り）

---

## Success Criteria

- **SC-001**: `make scraper-run` 実行後、5分以内に両社のレコードが `operation_statuses` に保存される
- **SC-002**: 同じデータを2回スクレイピングしても `operation_statuses` の件数が増えない（重複防止）
- **SC-003**: `scraper_logs` で実行履歴・エラー内容が確認できる
- **SC-004**: 1社のサイトがダウンしても、もう1社のスクレイピングは正常完了する
