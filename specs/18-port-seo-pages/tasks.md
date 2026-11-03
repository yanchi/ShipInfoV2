# Tasks: 港ごとのページと、検索で選ばれるタイトル・説明文

**Input**: [plan.md](plan.md)・[spec.md](spec.md)・[research.md](research.md)・[data-model.md](data-model.md)・[contracts/http-routes.md](contracts/http-routes.md)・[contracts/seo-meta.md](contracts/seo-meta.md)
**Tests**: 書く（SC-001・SC-005・SC-006 と contracts の表をテストで確かめる）

各フェーズの終わりに `git commit` する（Constitution V）。

## Phase 1: Setup

なし（新しいライブラリ・設定は無い）

## Phase 2: Foundational（港の slug・呼び名）

- [ ] T001 app/migrations/Version20261104000000.php：`ports` に `slug VARCHAR(32) NULL`・`display_name VARCHAR(64) NULL` を足す → 7 港に data-model.md の値を入れる → 残った行を `CONCAT('port-', id)` で埋める → `slug` を NOT NULL にして UNIQUE（`UNIQ_PORTS_SLUG`）を付ける。down は 2 列を消す
- [ ] T002 app/src/Entity/Port.php：`slug`（`#[ORM\Column(length: 32, unique: true)]`、string）・`displayName`（`#[ORM\Column(length: 64, nullable: true)]`）と getter/setter、`getDisplayName(): string`（`displayName ?? name`）を足す
- [ ] T003 `grep -rn "new Port()" app/tests` で港を作っているテストを確かめる。今は app/tests/View/PortFilterTest.php だけで DB に保存しないので、slug は既定の `''` のままでよい。T004 のテストが落ちたときだけ `setSlug()` を足す
- [ ] T004 `make migrate`・`make lint-php`（Doctrine スキーマの検証）・`make test-php` を通してコミット

## Phase 3: User Story 1 - 島の名前で検索して、その港を出る便がすぐ分かる（P1）🎯 MVP

**Goal**: `GET /ports/{slug}` に港の呼び名入りのタイトル・h1・説明文で 1 港分のボードを出し、sitemap と港別ページ内のリンクからたどれるようにする（FR-001〜FR-008・FR-013a・FR-013b）
**Independent Test**: `/ports/kametoku` が亀徳の便だけを出し、title・h1・canonical が contracts のとおり。`/ports/xxx` は 404。sitemap に 7 港

- [ ] T005 [US1] app/src/Service/PortFilterResolver.php：`resolveForPort(Request, array $boardStops, Port $port): PortFilterResolution` を足す。港は引数、方向は `dir` クエリ（不正なら両方向）、`hasSaved` は Cookie が正しく読めたか。Cookie が不正なら消す Cookie を返す。Cookie は書かない（research R4）。あわせて `findDeparturePortBySlug(array $boardStops, string $slug): ?Port` を足す
- [ ] T006 [P] [US1] app/tests/Service/PortFilterResolverTest.php：`resolveForPort()` の URL 優先・Cookie を書き換えない・`dir` 不正で両方向・Cookie 不正で消す、`findDeparturePortBySlug()` の一致・不一致
- [ ] T007 [US1] app/src/Controller/StatusController.php：`#[Route('/ports/{slug}', name: 'app_status_port', requirements: ['slug' => '[a-z][a-z0-9-]*'], methods: ['GET'])]` の `port()` を足す。出発港に無ければ `createNotFoundException`。描画は `ports()` と同じ変数に `currentPort` を足して `status/ports.html.twig`、Cookie・`varyByCookie()` も同じ。`ports()` と重なる組み立ては private メソッドにまとめる。`ports()` 側は `currentPort: null`
- [ ] T008 [P] [US1] app/templates/status/_port_links.html.twig（新規）：`portOptions` と `currentPort` を受け、contracts/seo-meta.md の `<nav class="port-links" aria-label="港ごとのページ">` を出す（文字は `port.displayName`、いまの港は `<span aria-current="page">`）。折り返すスタイルを app/templates/_site_styles.html.twig に足す
- [ ] T009 [US1] app/templates/status/ports.html.twig：`currentPort` があれば title `<呼び名>発 フェリー運航状況（今日・明日）`・h1 `<呼び名>発の運航状況`・港の説明文（contracts/seo-meta.md）。日付ボタンの下・フォームの上に `_port_links` を入れる
- [ ] T010 [US1] app/templates/base.html.twig：ナビの「港別」の active・`aria-current` を `currentRoute in ['app_status_ports', 'app_status_port']` で判定する
- [ ] T011 [US1] app/src/Controller/SeoController.php：`RouteStopRepository::findBoardStops()` の出発港（`PortFilterResolver::departurePorts()`）ごとに `app_status_port` の URL（priority 0.9）を、港別の次・各社の前に足す
- [ ] T012 [US1] app/tests/Controller/StatusControllerTest.php：`/ports/kametoku` の 200・亀徳の行だけ・title・h1・canonical（`?dir=up` 付きでもクエリ無し）・ナビの aria-current・港リンク（亀徳は span で「徳之島（亀徳港）」、6 港は a で文字が呼び名）、Cookie に別の港があっても URL の港を出し「保存を解除」が出る、`/ports/xxx` と `/ports/filter`（GET）の 404、`Cache-Control: private`・`Vary: Cookie`
- [ ] T013 [P] [US1] app/tests/Controller/SeoControllerTest.php：sitemap に `/ports/<slug>` が出発港の数だけ載る
- [ ] T014 [US1] `make test-php`・`make phpstan`・`make cs-php`・`make lint-php` を通してコミット

## Phase 4: User Story 2 - 検索結果のタイトルを見て「今日・明日の運航状況が分かる」と思える（P1）

**Goal**: トップ・港別・会社別・既定のタイトルと説明文を contracts/seo-meta.md にする（FR-014〜FR-021）
**Independent Test**: 各ページの `<title>`・`meta description` が contracts のとおりで、HTML に「運行」が 0 件

- [ ] T015 [P] [US2] app/config/packages/twig.yaml：`site_top_title`・`title_suffix` を contracts/seo-meta.md の値にし、コメントを「18-port-seo-pages で検索向けに変えた（それ以外は V1 のまま）」に直す
- [ ] T016 [P] [US2] app/templates/base.html.twig・app/templates/status/index.html.twig・app/templates/status/company.html.twig・app/templates/status/ports.html.twig（全港）：説明文と会社別・全港のタイトルを contracts/seo-meta.md にする
- [ ] T017 [US2] app/tests/Controller/StatusControllerTest.php・app/tests/Controller/ErrorPageTest.php：タイトルの期待値を直し、トップ・港別・会社別・港のページ・エラーページ（404）で description と「運行」が 0 件であることを確かめるテストを足す（SC-005）
- [ ] T018 [P] [US2] specs/7-v1-branding/spec.md の FR-004 の下に「18-port-seo-pages で置き換えた」と書く。CLAUDE.md の「サイト名・タイトル・OG の文言は V1 を引き継ぎ」を「サイト名・OG は V1 を引き継ぎ、タイトル・説明文は 18-port-seo-pages で検索向けにした」に直す
- [ ] T019 [US2] `make test-php`・`make lint-php` を通してコミット

## Phase 5: User Story 3 - 今まで使っていた港別ページ・保存した港がそのまま使える（P2）

**Goal**: 古い `/ports?port=<id>` を 301、フォームの移り先を `/ports/{slug}`、トップの「4日分を見る」を港のページにする（FR-009〜FR-013）。US1 の slug・ルートが前提
**Independent Test**: contracts/http-routes.md の GET /ports と POST /ports/filter の表がすべてテストで通る

- [ ] T020 [US3] app/src/Service/PortFilterResolver.php：`resolve()` で `port` が出発港の ID なら `redirectTo = /ports/<slug>`（`dir` が正しければ `?dir=`）を返す。`url()` を、港があれば `/ports/<slug>`（＋`?dir=`）、無ければ今までどおりにする（research R5・R6）
- [ ] T021 [US3] app/src/Controller/StatusController.php：`ports()` で `redirectTo` があれば 301 の `RedirectResponse`（消す Cookie があれば付け、`varyByCookie()`）を返す
- [ ] T022 [US3] app/templates/status/index.html.twig：「4日分を見る」を、保存した港があれば `path('app_status_port', {slug: …, dir: …})`、方向だけの保存なら `path('app_status_ports')` にする。港の Port は、トップに渡している `portOptions` から `portFilter.portId` で引く（コントローラーは変えない）
- [ ] T023 [US3] app/tests/Service/PortFilterResolverTest.php：`resolve()` の転送先（港あり・dir あり・dir 不正・`all`・不正な番号・dir だけ）と `submit()` の移り先を contracts/http-routes.md の表どおりに直す・足す
- [ ] T024 [US3] app/tests/Controller/StatusControllerTest.php：`/ports?port=<id>&dir=down` の 301 と Location、`/ports?port=all`・`/ports?port=999`・`/ports`（Cookie あり）の 200、フォームの 303 の Location、トップの「4日分を見る」の href。今の `/ports?port=<id>` を開いて中身を見ているテストは `/ports/<slug>` に直す
- [ ] T025 [US3] `make test-php`・`make phpstan` を通してコミット

## Phase 6: Polish

- [ ] T026 quickstart.md の手順をローカル（`make up`）で通す。375px 幅で港リンクに横スクロールが出ないことも見る
- [ ] T027 `make test-php`・`make phpstan`・`make cs-php`・`make lint-php`・`make verify-prod` を通し、tasks.md のチェックを付けてコミット

## Dependencies & Execution Order

- Phase 2 → US1 → US3（US3 は US1 の slug・`app_status_port` を使う）
- US2 は Phase 2 のあと、US1・US3 と独立（T016 の ports.html.twig だけ T009 と同じファイルなので、US1 のあとにする）
- [P] は別ファイルで先行タスクに依存しないもの

## Parallel Example: User Story 1

```text
T006（PortFilterResolverTest）・T008（_port_links）・T013（SeoControllerTest）は T005 のあと並行できる
```

## Implementation Strategy

1. Phase 2 + US1 で港のページが公開できる状態（MVP）。この時点でもフォームは古い URL に移り、Cookie も今までどおり動く
2. US2 でタイトル・説明文を変える（小さく、CTR に直接効く）
3. US3 で古い URL とフォームを新しい URL にそろえる
4. 公開後、quickstart.md の「公開後」の手順で Search Console に sitemap を送り直す
