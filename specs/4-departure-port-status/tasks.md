# Tasks: 出発港別の運航情報表示

**Input**: Design documents from `specs/4-departure-port-status/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/http-routes.md, quickstart.md

**Tests**: 入れる。plan.md でテストファイルを明示していて、SC-004 で既存テストが全部通ることを求めているため。

**Story ラベル**: spec.md の User Story 番号（US1〜US5）。実装は依存関係の都合で US1 → US2 → US4 → US3 → US5 の順にする（US3 のマルエー側は、US4 の船と行の対応付けを使う）。

**コミット**: 各 Phase の Checkpoint でコミットする（constitution V）。

---

## Phase 1: Setup

**Purpose**: 実行環境と設定、テスト用の実ページの保存

- [X] T001 `docker-compose.yml` の `scraper` サービスの `environment` に `TZ: Asia/Tokyo` を追加する（research R6）。`docker compose up -d --force-recreate scraper` のあと、`docker compose exec scraper python -c "import datetime; print(datetime.datetime.now())"` がホストの JST と一致することを確認する
- [X] T002 [P] `scraper/scraper/config.py` の `Settings` に `marue_search_days_ahead: int`（環境変数 `MARUE_SEARCH_DAYS_AHEAD`、既定 3）、`marue_far_search_interval_hours: int`（`MARUE_FAR_SEARCH_INTERVAL_HOURS`、既定 6）、`marue_search_delay_seconds: float`（`MARUE_SEARCH_DELAY_SECONDS`、既定 0.5）を追加する（research R8）
- [X] T003 [P] 実サイトのページを取得して `scraper/tests/fixtures/` に保存する（UTF-8）。GET は `curl -s <URL> -o <保存先>`、マルエーの検索は `curl -s -X POST https://www.aline-ferry.com/search/result.php --data-urlencode "startDate=YYYY年MM月DD日" --data "startPort=<コード>&endPort=<コード>" -o <保存先>` で取る（日付は必ず `YYYY年MM月DD日` 形式）
  - `marix/list.html`：`https://marixline.com/service/`
  - `marix/upstream_conditional.html`：一覧からリンクされている上り便の詳細ページ（与論・和泊が条件付の例。手に入らなければ取得した詳細ページの `div.single` の class を書き換えて作る）
  - `marix/downstream.html`：一覧からリンクされている下り便の詳細ページ
  - `marue/kagoshima.html`：`https://www.aline-ferry.com/kagoshima/`
  - `marue/ship_detail_normal.html`：鹿児島航路ページの船ブロックのリンク先（平常時。定型の注意書きを含む全文）
  - `marue/search_ship.html`：船名が出る検索結果（例：名瀬=70 → 那覇=83、マルエーの運航日）
  - `marue/search_other_company.html`：「※下記参照／マリックスライン㈱」の検索結果
  - `marue/search_empty.html`：`tbody` が空の検索結果（実際のページの `tbody` の中身を消して作る）

**Checkpoint**: scraper が JST で動いている。fixture が揃っている → コミット

---

## Phase 2: Foundational（ブロッキング前提）

**Purpose**: スキーマ、エンティティ・モデル、港名の正規化、港別 upsert の共通処理、バッジの共通化

**⚠️ CRITICAL**: この Phase が終わるまで US の実装を始めないこと

- [X] T004 Doctrine マイグレーション `app/migrations/Version20261001000000.php` を作る（data-model.md に従う）
  - `ports`（`name` UNIQUE、`aliases` JSON）
  - `port_company_codes`（UNIQUE(port_id, ferry_company_id)）
  - `route_stops`（UNIQUE(route_id, port_id)、UNIQUE(route_id, stop_order)）
  - `departure_statuses`（UNIQUE(route_id, port_id, departure_date, ship_name)、INDEX(departure_date, port_id)、`status` は NULL 可、`operated_by_company_id` は NULL 可の FK）
  - `routes.direction` VARCHAR(8) NULL を追加
  - 初期データはこのマイグレーションだけで入れる（`01_schema.sql` / `02_seed.sql` には足さない。`make init` では init スクリプトの後に `make migrate` が走るので、両方に書くと二重に適用されて衝突するため）
    - `ports` 7件と別名（research R5）：そのまま INSERT
    - 港コード（research R3）：`INSERT ... SELECT` で `ferry_companies.scraper_class = 'MarueFerry'` の会社があるときだけ入れる
    - `routes.direction`：`origin_port` が「鹿児島」なら `down`、「那覇」なら `up` を UPDATE
    - `route_stops`：`INSERT ... SELECT` で、`direction` の付いた既存の routes ごとに入れる（data-model.md の表）
    - ID は決め打ちしない。routes や ferry_companies が空のテスト用 DB（`shipinfo_test`）でも、外部キーエラーにならずに通ること
  - `down()` でテーブル削除と列削除をする
- [X] T005 [P] `app/src/Enum/RouteDirectionEnum.php`（`Down = 'down'`、`Up = 'up'`、ラベル「下り（那覇行き）」「上り（鹿児島行き）」を返す `label()`）と `app/src/Enum/DepartureDisplayStateEnum.php`（`Status`、`Scheduled`、`NoInfo`、`NoService`）を作る
- [X] T006 [P] `app/src/Entity/Port.php`（`name`、`aliases` は json 型）と `app/src/Entity/PortCompanyCode.php` を作る。マッピングは T004 のスキーマと一致させる
- [X] T007 [P] `app/src/Entity/RouteStop.php`（`route`、`port`、`stopOrder`、`dayOffset`）を作る。`app/src/Entity/Route.php` に `direction`（`RouteDirectionEnum`、nullable）と `stops`（OneToMany、`stopOrder` 昇順）を足す
- [X] T008 [P] `app/src/Entity/DepartureStatus.php` を作る（data-model.md の全カラム。`status` は `OperationStatusEnum`、nullable）。リポジトリクラスとして `app/src/Repository/DepartureStatusRepository.php` と `app/src/Repository/RouteStopRepository.php` の雛形も作る
- [X] T009 [P] `scraper/scraper/db/models.py` に SQLAlchemy の `Port`、`PortCompanyCode`、`RouteStop`、`DepartureStatus` を追加して、`Route` に `direction` と `stops` リレーションを足す。カラム名・型・ユニーク制約は T004 と一致させる（`aliases` は `JSON` 型。SQLite のテストでも動くこと）
- [X] T010 [P] `docker/mysql/init/01_schema.sql` の冒頭コメントに「港別の新しいテーブルと初期データは Doctrine マイグレーション（`app/migrations/Version20261001000000.php`）で作る。ここには書かない」と追記する（init スクリプトとマイグレーションの二重適用を防ぐため）
- [X] T011 `make migrate` を実行して、テスト用 DB にも `docker compose exec php bin/console doctrine:migrations:migrate --env=test --no-interaction` で適用する（routes が空でも通ること）。続けて `make migrate-diff` で差分が出ない（エンティティとマイグレーションが一致している）ことを確認する。差分が出たらエンティティ側（`app/src/Entity/`）を直す
- [X] T012 [P] `scraper/scraper/utils/ports.py` に `PortResolver` を作る。`PortResolver.from_session(session)` で ports を読み込んで、`resolve(text) -> Port | None` は別名の長い順にマッチ（「鹿児島新港」を「鹿児島」より先に）、`find_all(text) -> list[Port]` は文中の港を重複なしで出現順に返す。テストは `scraper/tests/test_ports.py`（表記揺れ全部、「鹿児島新港」の優先、未知の港名 → None）
- [X] T013 `scraper/scraper/scrapers/base.py` に港別の共通処理を足す
  - `parse_departures(self) -> list[dict]`：デフォルトは `[]`
  - `_upsert_departures(records) -> tuple[int, int]`：data-model.md の更新ルール1〜5・7
    - `content_hash` は status・status_detail・ship_name・各日時・operated_by_company_id の SHA-256
    - ハッシュが同じなら `checked_at` だけ更新
    - `freeze_after_departure=True` で既存行の `scheduled_departure_at < now` なら、その行は一切更新しない（`checked_at` も進めない）。既存行が無くて、受け取った `scheduled_departure_at < now` なら INSERT しない
    - `replace_scope` があれば、同じ (route_id, port_id, departure_date) で今回のレコードに無い ship_name の行を削除する。**ただし `scheduled_departure_at < now` の行は削除しない**
  - `run()`：`_upsert()` のあとに `self.session.flush()` を明示的に呼ぶ（航路単位のエラーは今までどおり外側の except で failed にする）。そのあと `with self.session.begin_nested():`（SAVEPOINT）の中で `parse_departures()` と `_upsert_departures()` を実行する。例外は SAVEPOINT の外で捕まえて、`scraper_log.error_message` に `departures: <msg>` を入れる。航路単位の結果は success のまま保存する（Session が失敗状態のまま残って、最後の commit が失敗しないこと）。SQLite のテストで SAVEPOINT が効くように、必要なら `scraper/tests/conftest.py` に pysqlite の SAVEPOINT 対応（SQLAlchemy ドキュメントの `do_begin` イベントのレシピ）を入れる
  - `fetch()` / `parse()` のシグネチャは変えない
- [X] T014 `scraper/tests/test_base_departures.py` を作る。T013 のルールを全部テストする
  - 新規 INSERT
  - 同じハッシュなら `checked_at` だけ進む（`scraped_at` は変わらない）
  - ハッシュが違えば両方進む
  - freeze で出港済みの行の status が変わらない
  - freeze した行は、`checked_at` も `scraped_at` も `content_hash` も変わらない（FR-014：表示中のステータスを最後に確認した時刻を保つ）
  - replace_scope で古い ship_name の行が消える
  - replace_scope でも、出港済みの行は消えない
  - 既存行が無い出港済みのレコード（`freeze_after_departure=True`）は INSERT されない
  - 航路単位の `_upsert()` の flush で起きたエラーは、港別のエラーとしては扱われず、今までどおり failed になる
  - `_upsert_departures` で DB エラー（例：一意制約違反）が起きても、航路単位の `operation_statuses` と `scraper_logs`（`error_message` 入り）がコミットされる
  - parse_departures の例外で航路単位が保存されて error_message が入る
- [X] T015 [P] バッジを `app/templates/status/_status_badge.html.twig` に切り出して、`app/templates/status/index.html.twig` と `app/templates/status/company.html.twig` から `include` する。表示される HTML は変えない。パーシャルの引数は次の2つ（3画面で共通）
  - `state`：`DepartureDisplayStateEnum|null`。null のときは `status` だけで判定する（既存2画面の呼び方）
  - `status`：`OperationStatusEnum|null`。`state` が null で `status` も null → 「情報なし」（既存の挙動）
  - `state` が `Status` → `status` のバッジ、`Scheduled` → 「運航予定」、`NoInfo` → 「情報なし」、`NoService` → 「便なし」
- [X] T016 `make test-php`（`app/tests/`）と `make test-scraper`（`scraper/tests/`）で既存テストが全部通ることを確認する

**Checkpoint**: マイグレーションが適用され、既存テストが全部通る → コミット

---

## Phase 3: User Story 1 - 2社の便を1つのページで港ごとに確認できる (Priority: P1) 🎯 MVP

**Goal**: `/ports` で、今日〜3日先の「方向 × 出発港」の行に、その日の運航会社の便を1行で出す。

**Independent Test**: AppFixtures またはテスト内で作った `departure_statuses` だけで、`/ports` が US1 のシナリオ1〜7 どおりに表示される（スクレイパーには依存しない）。

### Tests for User Story 1

- [X] T017 [P] [US1] `app/tests/Service/PortBoardBuilderTest.php` を作る。data-model.md の合成ルール1〜5 と US1 のシナリオを網羅する
  - 運航会社の便だけ出て、他社の「便なし」は出ない
  - 2社とも `no_service` → 便なし
  - 2社とも便あり → 2エントリ
  - `operated_by` あり・今日 → 「マリックスライン／情報なし」
  - `operated_by` あり・未来 → 「マリックスライン／運航予定」
  - `status` NULL → 運航予定
  - 行なし → 情報なし
  - 港の並びは stop_order 順で、終点は出ない
  - 日付は今日〜3日先だけ
- [X] T018 [P] [US1] `app/tests/Repository/DepartureStatusRepositoryTest.php` を作る。`findForBoard()` が期間内の行だけを route・port・company 付きで返すこと、過去の日付が含まれないこと

### Implementation for User Story 1

- [X] T019 [P] [US1] ビューモデルを `app/src/View/` に作る：`PortBoard`、`PortBoardDay`、`PortBoardDirection`、`PortBoardRow`、`PortBoardEntry`（readonly、data-model.md の「表示用」の構造）
- [X] T020 [P] [US1] `app/src/Repository/RouteStopRepository.php` に `findBoardStops(): array` を実装する。`direction` のある有効な航路について、方向ごとに「終点を除いた出発港（stop_order 順）」と「終点の港」を返す。2社で順番が同じ前提で、方向ごとに最初の航路の順を使う
- [X] T021 [P] [US1] `app/src/Repository/DepartureStatusRepository.php` に `findForBoard(\DateTimeImmutable $from, int $days): array` を実装する。期間内の `departure_statuses` を route（ferryCompany 込み）・port・operatedByCompany と JOIN して、クエリ1本で取る
- [X] T022 [US1] `app/src/Service/PortBoardBuilder.php` に `build(array $boardStops, array $statuses, \DateTimeImmutable $today, int $days): PortBoard` を実装する（data-model.md の合成ルール1〜5、FR-010・018・019・021）。DB に依存しないこと
- [X] T023 [US1] `app/src/Controller/StatusController.php` に `#[Route('/ports', name: 'app_status_ports')] ports()` を足す。今日（`new \DateTimeImmutable('today')`）から4日分を Builder で組み立てて `status/ports.html.twig` に `board` と `today` を渡す
- [X] T024 [US1] `app/templates/status/ports.html.twig` を作る（contracts/http-routes.md の構成）
  - 日付セクション → 方向 → 出発港の行
  - 各エントリ：バッジ（`_status_badge` に `state` と `status` を渡す。`Scheduled` の「運航予定」は緑系以外の中立の見た目で新しく追加）、「船名／会社名」、出港予定時刻と到着予定時刻（日付が違えば「翌H:i着」）、詳細テキスト、「n/j H:i時点」（checked_at）
  - データが無いときの表示と「← トップへ戻る」
- [X] T025 [US1] `app/templates/status/index.html.twig` の見出しの下に「港別に見る →」リンク（`path('app_status_ports')`）を足す。カードの構成は変えない
- [X] T026 [US1] `app/tests/Controller/StatusControllerTest.php` に `/ports` のテストを足す
  - 200 が返る
  - 今日〜3日先の見出しが出て、昨日は出ない
  - 運航会社の便が出て、他社の「便なし」は出ない
  - 運航予定のバッジ
  - 「時点」の表示
  - トップに `/ports` へのリンクがある
  - あわせて `tearDown()` を直して、`departure_statuses`・`route_stops` を routes より先に削除する
- [X] T027 [US1] `app/src/DataFixtures/AppFixtures.php` を更新する。T004 と同じ港・港コード・寄港順・direction を入れて、`/ports` の目視確認用に `departure_statuses` を作る（今日：マルエー運航・通常、マリックス `no_service` + `operated_by` なし／明日：マリックス運航・`operated_by` だけ分かってる行／3日先：マルエー `status` NULL）

**Checkpoint**: `make test-php` が全部通る。`make fixtures` のあと `/ports` が目視で US1 のシナリオどおりになっている → コミット

---

## Phase 4: User Story 2 - 自分の乗る港から船が出るか確認できる（マリックスライン）(Priority: P1)

**Goal**: マリックスラインの便別詳細ページから、港ごとのステータスと出港日時を `departure_statuses` に記録する。

**Independent Test**: `marix/*.html` の fixture で `MarixLine.parse_departures()` を実行して、出発港6行が正しいステータス・出港日時で作られる。

### Tests for User Story 2

- [X] T028 [P] [US2] `scraper/tests/test_marix_line.py` に港別のテストを足す
  - `upstream_conditional.html` → 上りの出発港6行（那覇・本部・与論・和泊・亀徳・名瀬）、与論・和泊が `delayed`、他は `operating`（US3 シナリオ4・SC-008）
  - 各行の `scheduled_departure_at` が「出港」の日時、`scheduled_arrival_at` が終点の「入港」日時
  - 終点（鹿児島）の行は作られない
  - 港の表記（「鹿児島新港」「名瀬港」）が正規化される
  - 詳細ページの取得に失敗したら、便ステータスを全出発港に当てはめて、日付は始発日 + day_offset、時刻は None（warning）
  - 寄港順に無い港は無視して warning
  - 既存の航路単位のテストが通る

### Implementation for User Story 2

- [X] T029 [US2] `scraper/scraper/scrapers/marix_line.py` の `fetch()` を拡張する。一覧の各 `div.status_single_cover a.status_single[href]` の詳細ページを取得して `self._detail_pages: dict[str, str | None]`（失敗は None + warning）に持たせる。戻り値は今までどおり一覧の HTML（`raw_html_hash` の意味は変えない）
- [X] T030 [US2] `scraper/scraper/scrapers/marix_line.py` に `parse_departures()` を実装する（research R1）
  - 一覧のブロックごとに、方向と始発日を今ある `_parse_direction` / `_parse_date` で決める
  - 詳細ページの `div.service > div.single` ごとに：`span.port_name` を `PortResolver` で港に直す → 状態は今ある `_parse_status_from_classes`（`div.single` の class）→ 説明は `div.exp`（operating のときは None）→「出港」と「入港」の `MM月DD日 HH:MM` を始発日の年で補う（始発日より前の月日なら翌年）
  - 寄港順のうち終点以外の港についてレコードを作る（`ship_name` は詳細ページから取れれば船名、無ければ空文字、`source_url` は詳細ページの URL、`freeze_after_departure=False`、`replace_scope=None`）
  - 詳細ページが無い便は予備ルートで作る
- [X] T031 [US2] `scraper/scraper/scrapers/marix_line.py` の docstring に、詳細ページの構造と港別処理の説明を足す

**Checkpoint**: `make test-scraper` が全部通る。`make scraper-run` のあと `departure_statuses` にマリックスの行が入る → コミット

---

## Phase 5: User Story 4 - マルエーフェリーは出発港別の便検索で船と出港日時を決める (Priority: P1)

**Goal**: マルエーの便検索の日付形式を直して、航路単位の便有無を方向ごとに正しくし、港別の行を便検索から作る。

**Independent Test**: `marue/*.html` の fixture で `MarueFerry` を実行して、US4 のシナリオ1・2・6〜9 どおりの航路単位・港別のレコードができる。

### Tests for User Story 4

- [X] T032 [P] [US4] `scraper/tests/test_marue_ferry.py` の既存の検索サンプル（`HTML_SEARCH_HAS_SERVICE` など）を、実際の構造（会社名の列あり、`search_*.html` の fixture）に置き換える。今の挙動が変わるテストは、新しい仕様（他社運航 → `no_service`）に合わせて直す。テストを足す
  - POST の `startDate` が `YYYY年MM月DD日` になっている
  - 方向ごとの便有無（下りはマルエー運航、上りは他社運航 → 下りは船ステータス、上りは `no_service`）
  - 港別：船名あり → その船の船ステータス（US4 シナリオ1・8）
  - 他社運航 → `no_service` + `operated_by` = マリックスラインの id（シナリオ7）
  - 結果0件 → `no_service`
  - 船名が船ブロックに無い → `unknown` + warning（シナリオ6）
  - 同じ船の2便目以降 → `status` None（FR-021）
  - `freeze_after_departure=True` と `replace_scope` が付いている
  - 2〜3日先の検索はキーごとに判定する：`checked_at` が6時間以内のキーは検索しない、行が無いキーと古いキーは検索する（一部のキーだけ失敗した次の実行で、失敗したキーだけ取り直される）
  - 検索の間に待ちが入る（`time.sleep` をモック）

### Implementation for User Story 4

- [X] T033 [US4] `scraper/scraper/scrapers/marue_ferry.py` に便検索のヘルパーを作る
  - `_format_search_date(d) -> "YYYY年MM月DD日"`
  - `_search(start_code, end_code, d) -> list[SearchRow] | None`（None = 取得・解析の失敗、`[]` = 便0件）：`SearchRow` は `ship_name`、`company_name`、`is_other_company`、`departure_at`、`arrival_at`。「YYYY年M月D日 HH:MM」を解析する。`table.s-result` が無ければ None を返して warning
  - 呼び出しごとに `settings.marue_search_delay_seconds` だけ待つ
- [X] T034 [US4] `scraper/scraper/scrapers/marue_ferry.py` の `fetch()` を書き直す
  - 港コードと寄港順を DB から読む
  - 方向 × 終点以外の港 × 日付（今日・明日は毎回、2〜3日先は、検索キー (route, port, departure_date) ごとに、そのキーの `departure_statuses` が無いか `checked_at` が `marue_far_search_interval_hours` より古ければ）で `_search()` して `self._searches` に持たせる
  - 鹿児島航路ページを取って、船ブロック（船名・タグ・抜粋・詳細ページの URL）を `self._ships` に持たせる
  - 各船の詳細ページを取って `self._ship_details` に持たせる
  - 戻り値は鹿児島航路ページの HTML に、今日の始発港2つの検索結果を正規化した文字列をつなげたもの（方向ごとの便有無が変わったら `raw_html_hash` が変わるように）
- [X] T035 [US4] `scraper/scraper/scrapers/marue_ferry.py` の `parse()` を方向ごとの判定に書き直す（research R10）
  - 今日の「鹿児島→那覇」「那覇→鹿児島」の検索結果に、マルエーの行があればその船の船ステータス（船名で対応付け。無ければ `unknown`）
  - 他社運航のみ、または0件なら `no_service`
  - 検索に失敗（None）したら、今の安全側の挙動（船ステータスのうち一番重いもの）にして warning
  - `_check_service()` と古い Step 1 は消す
- [X] T036 [US4] `scraper/scraper/scrapers/marue_ferry.py` に `parse_departures()` を実装する（research R9）
  - 検索結果ごとにレコードを作る
  - 便を `(ship_name, route_id, arrival_at)` で特定して、船ごとに `arrival_at > now` の一番早い便を「今の便」にする
  - 今の便の行には船ステータス（この Phase では港別情報なし）と抜粋を入れて、それより後の便は `status=None`
  - 他社運航は `no_service` + `operated_by_company_id`（`ferry_companies.scraper_class = 'MarixLine'` の id）
  - 0件は `no_service`
  - 全部に `freeze_after_departure=True` と `replace_scope=(route_id, port_id, departure_date)`、`source_url` は `SEARCH_URL`
- [X] T037 [US4] `scraper/scraper/scrapers/marue_ferry.py` の docstring を、新しい処理の流れ（便検索 → 船 → 船ステータス、日付形式の注意）に書き直す

**Checkpoint**: `make test-scraper` が全部通る。`make scraper-run` のあと、マルエーの港別の行と、方向ごとの航路単位の行が入る → コミット

---

## Phase 6: User Story 3 - 条件付寄港地などの港別情報が港ごとに区別される (Priority: P1)

**Goal**: マルエーの運航状況テキストから港別情報（条件付寄港・抜港・港変更）を抜き出して、その船の行に反映する（マリックス側は US2 で詳細ページの港別ステータスとして対応済み）。

**Independent Test**: `port_notice` の単体テストと、テキストを差し替えた fixture での `MarueFerry.parse_departures()` で、US3 のシナリオ1〜3 と US4 のシナリオ3〜5 どおりになる。

### Tests for User Story 3

- [ ] T038 [P] [US3] `scraper/tests/test_port_notice.py` を作る
  - `marue/ship_detail_normal.html`（定型の注意書きを含む全文）→ 港別情報0件（誤検出が無いこと）
  - 「条件付寄港地: 和泊港、与論港」→ 和泊・与論が条件付
  - 「和泊港・与論港は条件付寄港。」→ 同じ結果
  - 「与論港は抜港」→ 与論が抜港
  - 「亀徳港から平土野港へ港変更」→ 亀徳が港変更、変更先は平土野
  - 「港変更がある場合、亀徳港から平土野港になります」→ 0件（仮定の文）
  - 同じ港に条件付と抜港 → 抜港を採用
  - 航路に無い港名だけの文 → 0件
- [ ] T039 [P] [US3] `scraper/tests/test_marue_ferry.py` に港別情報の反映テストを足す（US3 シナリオ1〜3、US4 シナリオ3〜5）
  - 条件付の船で和泊・与論の記載 → その方向の和泊・与論だけ `delayed`、他は `operating`
  - 条件付で記載なし → 全港 `delayed`
  - 欠航の船 → 記載があっても全港 `cancelled`
  - 抜港 → その港だけ `cancelled`、他は船ステータス
  - 港変更 → `delayed` で、詳細に変更先
  - 他方向の船の情報は混ざらない
  - パターンに当てはまらない条件付のテキスト → 船ステータス + `port_notice_unmatched` の warning

### Implementation for User Story 3

- [ ] T040 [US3] `scraper/scraper/utils/port_notice.py` を作る（research R4）
  - `extract_notice_text(excerpt, detail_html) -> str`：詳細ページの `div.status-archive` で、`h4` の後から「台風の影響や」を含む段落の手前までの本文と、抜粋をつなげる。区切りが見つからなければ抜粋だけ
  - `extract_port_notices(text, resolver) -> list[PortNotice]`：`PortNotice` は `port_id`、`kind`（`conditional` / `skip` / `change`）、`change_to`、`sentence`。文に分けて、「場合」「ことがあります」「可能性」を含む文は除外する。`抜港` → skip、`港変更`・`寄港地変更`・「〜港から〜港」→ change（後ろの港が変更先）、`条件付` → conditional。1つの港に複数あれば skip > change > conditional
- [ ] T041 [US3] `scraper/scraper/scrapers/marue_ferry.py` の `parse_departures()` で、今の便の行に港別情報を当てはめる（FR-006）
  - 船ステータスが `cancelled` / `suspended` / `no_service` → そのまま
  - そうでなければ、言及された港を skip → `cancelled`、change / conditional → `delayed`（詳細に元の文と変更先）にする
  - 船ステータスが `delayed` で港別情報が1件以上 → 言及の無い港は `operating`
  - 船ステータスが `delayed` で港別情報が0件 → 全港 `delayed` にして `port_notice_unmatched` の warning
  - 航路単位の `parse()` の挙動は変えない

**Checkpoint**: `make test-scraper` が全部通る → コミット

---

## Phase 7: User Story 5 - 途中港の実際の出発日・最終確認時刻で見られる (Priority: P1)

**Goal**: 日またぎ（下りの途中港は始発の翌日）、出港済みの便の確定、最終確認時刻が、スクレイパーから画面まで通しで正しいことを確かめる。

**Independent Test**: 下り便の fixture と、時刻を固定したテストで、US5 のシナリオ1〜6 どおりになる。

- [ ] T042 [P] [US5] `scraper/tests/test_marix_line.py` に日またぎのテストを足す
  - `marix/downstream.html` で、名瀬以降の行の `departure_date` が始発日の翌日になる
  - 12/31 始発・1/1 出港の年またぎ（fixture の日付を書き換えて作る）
  - 一覧から消えた便の行が `departure_statuses` から消されない（FR-013、`_upsert_departures` を通して確認）
- [ ] T043 [P] [US5] `scraper/tests/test_marue_ferry.py` に確定のテストを足す（US4 シナリオ9）。10/1 05:50 発の行が DB にある状態で、10/1 20:00 に船ステータスが `cancelled` に変わったデータで実行しても、その行の status は `operating` のまま、`checked_at` も出港前の最後の確認時刻のまま変わらない。さらに、出港後の検索でその便が返らなくなっても（結果0件や別の船）、その行は削除されない。また、DB に行が無い状態で 10/1 10:00 に初めて実行したとき、10/1 05:50 発の行は作られない（港別ページでは「情報なし」）
- [ ] T044 [P] [US5] `app/tests/Controller/StatusControllerTest.php` に表示のテストを足す
  - `scheduled_departure_at` が前日始発の便でも、その日の日付セクションに出る
  - `checked_at` が「n/j H:i時点」で出る
  - 到着が翌日なら「翌H:i着」で出る
- [ ] T045 [US5] JST の確認：`scraper/tests/test_base_departures.py` に、`datetime.now()` を 0:30（JST の想定）に固定して、`departure_date` と `checked_at` が同じ暦日で記録されるテストを足す。あわせて quickstart.md の JST 確認手順を実際に実行する

**Checkpoint**: `make test-scraper` と `make test-php` が全部通る → コミット

---

## Phase 8: Polish & Cross-Cutting

- [ ] T046 [P] `scraper/` で `black` と `ruff` を実行して、指摘を直す
- [ ] T047 [P] `specs/website/contracts/http-routes.md` の冒頭に、`/ports` は `specs/4-departure-port-status/contracts/http-routes.md` を参照する旨の1行を足す
- [ ] T048 quickstart.md の手順を全部実際に実行する（マイグレーション、`make scraper-run`、`/ports` の目視、SQL の確認）。2社の実データで US1 のシナリオ1・5・6 になっていることを確かめる
- [ ] T049 PR の説明（`specs/4-departure-port-status/` の成果物へのリンク付き）に、既存の表示への影響（マリックスの日には、トップと会社詳細のマルエーが「便なし」になる）と、港別情報の抽出は実例なしで作っていること（quickstart の改善手順）を書く

---

## Dependencies & Execution Order

```
Phase 1 Setup
   ↓
Phase 2 Foundational（T004 → T011 → T016。T005〜T010・T012・T015 は T004 の後に並行で進められる。T013 → T014）
   ↓
   ├─ Phase 3 US1（Web。スクレイパーに依存しない）
   ├─ Phase 4 US2（マリックス）
   └─ Phase 5 US4（マルエー）
           ↓
        Phase 6 US3（マルエー側は US4 の parse_departures を使う）
           ↓
        Phase 7 US5（US1・US2・US4 の上で通しの確認）
           ↓
        Phase 8 Polish
```

- US1・US2・US4 は Foundational が終われば並行で進められる（触るファイルが別：`app/` / `marix_line.py` / `marue_ferry.py`）
- US3 は US4 の後（T041 は T036 の `parse_departures()` を拡張する）。T040 の `port_notice.py` 単体は US4 と並行で進められる
- US5 は US1・US2・US4 の後

## Parallel Examples

**Phase 2（T004 の後）**:
```
T005 Enum / T006 Port エンティティ / T007 RouteStop エンティティ / T008 DepartureStatus エンティティ
T009 SQLAlchemy モデル / T010 schema コメント / T012 PortResolver / T015 バッジのパーシャル
```

**US1**:
```
T017 Builder のテスト / T018 Repository のテスト / T019 ビューモデル / T020 RouteStopRepository / T021 DepartureStatusRepository
```

**US2・US4・US3（別の人やエージェントで）**:
```
US2: T028 → T029 → T030
US4: T032 → T033 → T034 → T035 → T036
US3: T038 → T040（US4 と並行） → T039・T041（T036 の後）
```

## Implementation Strategy

**MVP（最初に出す範囲）**: Phase 1 → Phase 2 → US1 → US2 → US4
- この時点で `/ports` に2社の実データが出て、本機能の目的（2社の公式サイトを見に行かずに1サイトで確認）を満たす
- マルエーの港別情報（条件付寄港など）は船ステータスで表示される（取りこぼし側）

**次の段階**: US3（港別情報の抜き出し）→ US5（通しの確認）→ Polish

各 Phase の Checkpoint で `make test-scraper` と `make test-php` を実行してからコミットする。
