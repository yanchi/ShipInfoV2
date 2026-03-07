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

**サイト構造**（実サイト確認済み 2026-03-07）:
```html
<!-- 異常あり（条件付・欠航等）の場合 -->
<div class="status-archive">
  <h3>フェリーあけぼの鹿児島 - 名瀬 - 亀徳 - 和泊 - 与論 - 本部 - 那覇</h3>
  <h4>■3/6(金)下り便…条件付き運航</h4>
  <div class="status-detail">
    <div class="tag-list"><span class="tag-conditionally">条件付運航</span></div>
    <p>3月6日(金)18:00鹿児島新港発/下り便「フェリーあけぼの」は...</p>
    <p>・条件付寄港地 : 和泊港、与論港</p>
  </div>
  <p>2026年03月07日更新</p>
</div>

<!-- 通常運航の場合（status-detail なし） -->
<div class="status-archive">
  <h3>フェリー波之上鹿児島 - 名瀬 - 亀徳 - ...</h3>
  <h4>通常運航致しております。</h4>
  <p>2026年03月07日更新</p>
</div>
```

ステータス判定ロジック（h4 テキストから）:
- h4 に `…` がある場合（例: `■3/6(金)下り便…条件付き運航`）: `…` 以降のキーワードで判定
- h4 に `…` がない場合（例: `通常運航致しております。`）: h4 全体のキーワードで判定
- 日付がない h4 の場合: `valid_date = today`

キーワードと状態のマッピング:
- `欠航` → `cancelled`
- `条件付` → `delayed`
- `遅延` / `スケジュール変更` → `delayed`
- `運休` → `suspended`
- `通常` → `operating`

航路マッチング（h3/h4 テキスト + route.origin_port → route.id）:
- h3 は船名 + 寄港地リストを含む（例: `フェリーあけぼの鹿児島 - 名瀬 - 亀徳 - ...`）
- h4 の「下り便」/「上り便」で方向を判定し、`origin_port`（鹿児島/那覇）に対応する航路を選択
- 方向不明（通常運航の一括告知等）は上り・下り両方に同じデータを適用
- 同一 `route_id + valid_date` の重複は最初のもの優先

**Acceptance Scenarios**:

1. **Given** マルエーフェリーのサイトが正常な場合、**When** スクレイパーを実行、**Then** 各便の運航状況が `operation_statuses` テーブルに保存される
2. **Given** 同じHTMLを2回スクレイピング、**When** `raw_html_hash` が一致、**Then** 重複レコードは作成されない
3. **Given** サイトが503を返す場合、**When** スクレイパーを実行、**Then** リトライ（最大3回）後に `scraper_logs` にエラーが記録される

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

- HTML構造が変更された場合: パーサーログ（warning/debug）を残し、致命的例外時は `scraper_logs` を `failed` で記録。他社のスクレイピングは継続する
- ネットワークタイムアウト/5xx: `requests + urllib3 Retry` により最大3回リトライ（backoff_factor=1.0）
- 日付解析の失敗:
  - MarixLine: warning ログを残してそのレコードをスキップ
  - MarueFerry: h4 から日付が取れない場合は `valid_date = today` を使用
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
- **マルエーフェリー**: h4 テキストの「下り便」/「上り便」で判定。方向不明（通常運航の一括告知等）は上り・下り両方に同じデータを適用
- **マリックスライン**: div.info2 の「鹿児島X発」→ 下り、「那覇X発」→ 上り

※ `origin_port` カラムで上り・下りを区別（鹿児島発 = 下り、那覇発 = 上り）

---

## Success Criteria

- **SC-001**: `make scraper-run` 実行後、5分以内に両社のレコードが `operation_statuses` に保存される
- **SC-002**: 同じデータを2回スクレイピングしても `operation_statuses` の件数が増えない（重複防止）
- **SC-003**: `scraper_logs` で実行履歴・エラー内容が確認できる
- **SC-004**: 1社のサイトがダウンしても、もう1社のスクレイピングは正常完了する
