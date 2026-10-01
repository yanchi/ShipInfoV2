# Data Model: 出発港別の運航情報表示

**Feature**: 4-departure-port-status
**Date**: 2026-10-01

スキーマは Doctrine Migration で管理し、SQLAlchemy モデルも同じ内容に揃える（既存の運用どおり）。

```
ferry_companies 1──* routes 1──* route_stops *──1 ports 1──* port_company_codes *──1 ferry_companies
                         │                         │
                         └──* departure_statuses *─┘
                         └──* operation_statuses（既存・変更なし）
departure_statuses *──0..1 ferry_companies（operated_by_company_id：他社運航の目印）
```

---

## 新規: `ports`

航路上の港のマスタ。

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | INT UNSIGNED | PK, AI | |
| name | VARCHAR(64) | NOT NULL, UNIQUE | 表示名（例：`名瀬`） |
| aliases | JSON | NOT NULL | 表記揺れ（例：`["名瀬港","名瀬"]`）。スクレイパーの正規化に使う |
| created_at / updated_at | DATETIME | NOT NULL | |

**初期データ**: 鹿児島・名瀬・亀徳・和泊・与論・本部・那覇（別名は research R5）

**ルール**: 別名は長いものから順にマッチさせる。どの港の別名ともぶつからないこと。

---

## 新規: `port_company_codes`

会社ごとの港の外部コード（今はマルエーの便検索用だけ）。

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | INT UNSIGNED | PK, AI | |
| port_id | INT UNSIGNED | FK → ports, NOT NULL | |
| ferry_company_id | INT UNSIGNED | FK → ferry_companies, NOT NULL | |
| external_code | VARCHAR(32) | NOT NULL | 例：名瀬 = `70` |

UNIQUE (`port_id`, `ferry_company_id`)

**初期データ**（マルエーフェリー）: 鹿児島 50 / 名瀬 70 / 亀徳 78 / 和泊 80 / 与論 82 / 本部 84 / 那覇 83

---

## 変更: `routes`

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| direction | VARCHAR(8) | NULL 可 | `down`（那覇行き）/ `up`（鹿児島行き）。港別ページのセクション分けに使う |

既存の4件（id 1〜4）にマイグレーションで値を入れる。NULL の航路は港別ページの対象外にする。

---

## 新規: `route_stops`

航路（会社 × 方向）ごとの寄港順と日数オフセット。

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | INT UNSIGNED | PK, AI | |
| route_id | INT UNSIGNED | FK → routes, NOT NULL | |
| port_id | INT UNSIGNED | FK → ports, NOT NULL | |
| stop_order | SMALLINT | NOT NULL | 1 = 始発港。最大値が終点（到着港） |
| day_offset | SMALLINT | NOT NULL, DEFAULT 0 | 始発日から何日後にこの港を出るか（予備用、research R3） |

UNIQUE (`route_id`, `port_id`), UNIQUE (`route_id`, `stop_order`)

**ルール**:
- 出発港の行になるのは終点以外の寄港地（FR-001・FR-002）。
- 港別ページの並び順は `stop_order`。2社で寄港順が同じ前提（spec の Assumptions）。違った場合は、その日付で最初に見つかった航路の順を使う。

**初期データ**（routes 1〜4 すべて同じ港の並び。方向で順番が逆になる）:

| 方向 | stop_order: 港（day_offset） |
|---|---|
| down | 1 鹿児島(0) / 2 名瀬(1) / 3 亀徳(1) / 4 和泊(1) / 5 与論(1) / 6 本部(1) / 7 那覇(1) |
| up | 1 那覇(0) / 2 本部(0) / 3 与論(0) / 4 和泊(0) / 5 亀徳(0) / 6 名瀬(0) / 7 鹿児島(1) |

---

## 新規: `departure_statuses`

会社 × 方向 × 出発港 × 出港日 × 船 の港別ステータス（spec の Departure Status）。

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK, AI | |
| route_id | INT UNSIGNED | FK → routes, NOT NULL | 会社と方向はここから決まる |
| port_id | INT UNSIGNED | FK → ports, NOT NULL | 出発港 |
| departure_date | DATE | NOT NULL | その港の出港日（JST） |
| ship_name | VARCHAR(255) | NOT NULL, DEFAULT `''` | 船名。便が無い行は空文字 |
| status | VARCHAR(32) | **NULL 可** | `OperationStatusEnum` の値。**NULL = 運航予定（未発表）** |
| status_detail | LONGTEXT | NULL 可 | 公式の説明文・港別情報の元テキスト |
| scheduled_departure_at | DATETIME | NULL 可 | 出港予定日時（JST） |
| scheduled_arrival_at | DATETIME | NULL 可 | 到着港への到着予定日時（JST） |
| operated_by_company_id | INT UNSIGNED | FK → ferry_companies, NULL 可 | `no_service` の行で、他社が運航していると分かっている場合の会社（マルエーの「※下記参照」） |
| source_url | VARCHAR(512) | NULL 可 | |
| content_hash | CHAR(64) | NOT NULL | status, status_detail, ship_name, 各日時, operated_by の SHA-256 |
| scraped_at | DATETIME | NOT NULL | 最後に内容が変わった時刻 |
| checked_at | DATETIME | NOT NULL | 最後に公式サイトで確認した時刻（FR-014 の表示用） |
| created_at / updated_at | DATETIME | NOT NULL | |

UNIQUE (`route_id`, `port_id`, `departure_date`, `ship_name`)
INDEX (`departure_date`, `port_id`)

**状態の意味**:

| status | operated_by_company_id | 意味 |
|---|---|---|
| `operating` / `delayed` / `cancelled` / `suspended` / `unknown` | NULL | 発表済みのステータス |
| NULL | NULL | 運航予定（予定は分かってるけど、ステータスは未発表。FR-021） |
| `no_service` | NULL | この会社はこの日・港に便が無い |
| `no_service` | 他社 id | この会社は便が無くて、他社（id）が運航している（FR-015・018） |

**更新ルール**（スクレイパー側）:

1. 同じキーの行が無い → INSERT（`scraped_at` = `checked_at` = 今）
2. 行があって `content_hash` が同じ → `checked_at` だけ更新する
3. 行があって `content_hash` が違う → 内容と `scraped_at`・`checked_at` を更新する
4. **マルエーの出港済みの行**（`scheduled_departure_at` < 今）は、`status` / `status_detail` を更新しない（FR-020）。時刻と `checked_at` は更新する
5. **マルエーの検索の取り直し**：同じ (route, port, departure_date) で今回の検索結果に無い `ship_name` の行は削除する。検索結果が正なので、船の入れ替えや「※下記参照」から船名への変化で古い行が残らないようにする
6. マリックスは、一覧から消えた便の行を消さない（FR-013：最後のステータスを出し続ける）

---

## 既存: `operation_statuses`（スキーマ変更なし）

- 航路単位（会社 × 方向 × 日付）の記録を今までどおり続ける（FR-012、constitution III）。
- マルエーは日付形式の修正によって、方向ごとに正しく `no_service` が入るようになる（research R10）。
- `status_detail` には運航状況テキスト（抜粋）を今までどおり入れる。港別情報を後から解釈し直すための元データになる。

---

## 表示用（PHP、DB には持たない）

### `PortBoard`（港別ページのビューモデル）

```
PortBoard
└─ days: list<PortBoardDay>              // 今日〜3日先
   └─ date, directions: list<PortBoardDirection>   // down → up
      └─ direction, arrivalPortName, rows: list<PortBoardRow>   // stop_order 順
         └─ port: Port, entries: list<PortBoardEntry>
            └─ state: DepartureDisplayState
               companyName, shipName, departureAt, arrivalAt, detail, checkedAt
```

### `DepartureDisplayState`（PHP の backed enum、表示専用）

| 値 | ラベル | いつ出すか |
|---|---|---|
| `status`（+ `OperationStatusEnum`） | 既存ラベル | 発表済みのステータス |
| `scheduled` | 運航予定 | `status` が NULL |
| `no_info` | 情報なし | 運航会社は分かってるけど、その会社の行が無い（当日）／どの会社の行も無い |
| `no_service` | 便なし | 全社 `no_service` で、他社運航の目印も無い |

**合成ルール**（日付 × 方向 × 出発港ごと。FR-010・018・019・021）:

1. その (date, direction, port) の `departure_statuses` を全社分集める
2. `status != no_service`（NULL を含む）の行を、それぞれ1エントリにする（2社とも便があれば2エントリ。FR-019）
3. 2 でエントリが0件で、`operated_by_company_id` がある `no_service` 行があるとき → その会社のエントリを1件作る
   - date が今日以前 → `no_info`（「マリックスライン／情報なし」）
   - date が明日以降 → `scheduled`（「マリックスライン／運航予定」）
4. まだ0件で、`no_service` の行があるとき → `no_service` を1件
5. 行が1件も無いとき → `no_info` を1件（会社名なし）
