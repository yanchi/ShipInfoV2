# Tasks: 検索語に合わせた会社ページの説明文と船の名前

**Input**: [plan.md](plan.md)・[spec.md](spec.md)・[research.md](research.md)・[data-model.md](data-model.md)・[contracts/seo-meta.md](contracts/seo-meta.md)
**Tests**: 書く（SC-001 と contracts/seo-meta.md の表をテストで確かめる）

各フェーズの終わりに `git commit` する（Constitution V）。

## Phase 1: Setup

なし（新しいライブラリ・設定は無い）

## Phase 2: Foundational

なし（列・エンティティは US2 だけが使うので US2 に置く。US1 は今のエンティティのままでできる）

## Phase 3: User Story 1 - 会社名で検索して、公式より早く分かるページだと気づく（P1）🎯 MVP

**Goal**: 会社ページのタイトルに「リアルタイム」、説明文に公式にない価値を入れる。トップ・港別・港・会社の説明文に「運航（運行）状況」を 1 回だけ入れ、それ以外には「運行」を出さない（FR-001〜FR-004）
**Independent Test**: 会社ページの title が `<会社名> 運航状況 リアルタイム（今日・明日）` + suffix。`/`・`/ports`・`/ports/naze`・会社ページで、「運行」は meta description と og:description にだけあり、description に「運航（運行）状況」がちょうど 1 回

- [X] T001 [US1] app/templates/status/company.html.twig：title を `{{ company.name }} 運航状況 リアルタイム（今日・明日）`、description を `{{ company.name }}の運航（運行）状況をリアルタイムで。今日・明日の欠航・遅延を毎時更新し、今日から4日分を航路ごとにまとめて確認できます。` にする（contracts/seo-meta.md。「運航船：」の文は T009 で足す）
- [X] T002 [P] [US1] app/templates/status/index.html.twig：description の「（奄美航路）のフェリー運航状況。」を「（奄美航路）のフェリー運航（運行）状況。」にする。title は変えない
- [X] T003 [P] [US1] app/templates/status/ports.html.twig：description の全港版「出港時刻と運航状況。」→「出港時刻と運航（運行）状況。」、港版「今日・明日の運航状況と出港時刻。」→「今日・明日の運航（運行）状況と出港時刻。」にする。title・h1 は変えない
- [X] T004 [US1] app/tests/Controller/StatusControllerTest.php：期待値を直す。`testTopTitleAndDescription` の説明文、`testPageTitleFormat` と `testOgTagsAreNotDoubleEscaped` の会社ページのタイトル（`… 運航状況 リアルタイム（今日・明日） | 鹿児島〜奄美・沖縄フェリー運航情報`）。`grep -n "運航状況（今日・明日）\|運航状況。\|運航状況と" app/tests` でほかに古い文言を見ているテストが無いかも確かめる
- [X] T005 [US1] app/tests/Controller/StatusControllerTest.php：`testNoUnkoSpellingOnAnyPage` を `testUnkoSpellingOnlyInDescription` に書き換える（research R6）。`/`・`/ports`・`/ports/naze`・会社ページそれぞれで、(1) meta description に「運航（運行）状況」がちょうど 1 回、(2) og:description も同じ値、(3) レスポンスの本文から `<meta name="description" …>` と `<meta property="og:description" …>` の 2 つのタグを正規表現で消したあとに「運行」が無い（title・h1・本文に無い）、を確かめる
- [X] T006 [US1] app/tests/Controller/StatusControllerTest.php：会社ページの description が「<会社名>の運航（運行）状況をリアルタイムで。」で始まり、「今日・明日の欠航・遅延を毎時更新」「今日から4日分」を含むことを確かめるテストを足す
- [X] T007 [US1] `make test-php`・`make cs-php`・`make lint-php` を通してコミット

**Checkpoint**: US1 だけで公開できる（船の名前の無い今の会社ページでも FR-001〜FR-004 を満たす）

## Phase 4: User Story 2 - 船の名前・会社の別名で検索して、その会社のページにたどり着く（P2）

**Goal**: 会社ごとに船の名前・別名を持ち、会社ページの h1 のすぐ下の1行と description に出す（FR-005〜FR-008）
**Independent Test**: マルエーフェリーの会社ページに「運航船：フェリー波之上・フェリーあけぼの ／ 別名：Aライン（エーライン）・大島運輸（旧社名）」の1行があり、description の最後が「運航船：フェリー波之上・フェリーあけぼの。」。船の名前・別名が無い会社には1行も「運航船：」も出ない

- [X] T008 [US2] app/migrations/Version20261124000000.php（新規）：`ALTER TABLE ferry_companies ADD ship_names JSON DEFAULT NULL, ADD aliases JSON DEFAULT NULL`。そのあと data-model.md の表の値を `UPDATE ferry_companies SET ship_names = ?, aliases = ? WHERE scraper_class = ?` で入れる（`MarixLine` の `aliases` は NULL）。JSON は `json_encode($v, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR)` で作る。down は 2 列を消す。クラスの doc コメントに目的と「スクレイパーは読み書きしない」を書く（Version20261104000000.php と同じ書き方）
- [X] T009 [US2] app/src/Entity/FerryCompany.php：`#[ORM\Column(type: 'json', nullable: true)] private ?array $shipNames = null;` と `aliases` を足す。`getShipNames(): array`・`getAliases(): array`（`@return list<string>`。NULL は `[]`、空の文字列の要素は除いて `array_values`）、`setShipNames(array $names): static`・`setAliases(array $aliases): static`（`@param list<string>`。空の配列は NULL で持つ）
- [X] T010 [US2] `make migrate`・`make lint-php`（Doctrine スキーマの検証で差分が出ないこと）・`make check-schema`（スクレイパーのモデルが通ること）を通す。`make test-scraper` も通して、スクレイパーのテストが `ferry_companies` に行を入れても落ちないことを確かめる（research R2）
- [X] T011 [US2] app/templates/status/company.html.twig：description の最後に、`company.shipNames` が空でなければ `運航船：{{ company.shipNames|join('・') }}。` を足す（T001 の文の後ろ。空なら何も足さない）
- [X] T012 [US2] app/templates/status/company.html.twig：`.page-heading` の div のすぐ後に、船の名前か別名があれば `<p class="company-aliases small text-muted mb-4">` を出す。中身は contracts/seo-meta.md の表のとおり（`運航船：A・B`、`別名：C・D`、両方あれば ` ／ ` でつなぐ）。1行を出すときは `.page-heading` の `mb-4` を `mb-1` にして、運航状況の位置がほとんど変わらないようにする。両方無ければ `<p>` を出さず、`.page-heading` は `mb-4` のまま
- [X] T013 [US2] app/tests/Controller/StatusControllerTest.php：テストの会社に `setShipNames()`・`setAliases()` を付けて、(1) 両方あり：`.company-aliases` の文字が `運航船：船A・船B ／ 別名：別名A・別名B`、description の最後が `運航船：船A・船B。`、(2) 船だけ：`運航船：船A` だけで「別名：」が無い、(3) 別名だけ：`別名：別名A` だけで description に「運航船：」が無い、(4) 両方無し：`.company-aliases` が 0 個・description に「運航船：」が無い、(5) 船の名前に `<b>&` を入れても `.company-aliases` ではエスケープされ、meta description・og:description には `<b>&` のまま入る（二重にエスケープされない）、を確かめる
- [X] T014 [P] [US2] app/tests/Entity/FerryCompanyTest.php（新規）：`getShipNames()`・`getAliases()` が NULL で `[]`、空の文字列を除く、`setShipNames([])` のあと `getShipNames()` が `[]` を確かめる
- [X] T015 [US2] `make test-php`・`make phpstan`・`make cs-php` を通してコミット

**Checkpoint**: 2 社の会社ページに船の名前・別名が出る

## Phase 5: Polish

- [X] T016 [P] specs/18-port-seo-pages/spec.md：Clarifications の「運行」の項目の下に「→ 19-search-query-wording で、description（と og:description）にだけ『運航（運行）状況』を 1 回出すように変えた。title・h1・本文は『運航』のまま」と追記する
- [X] T017 [P] CLAUDE.md：「重要な設計決定」のサイト名・OG の行の「（タイトル・説明文は 18-port-seo-pages で検索向けにした）」を「（タイトル・説明文は 18-port-seo-pages・19-search-query-wording で検索向けにした。『運行』は description にだけ出す）」にする。会社の船の名前・別名が `ferry_companies.ship_names`・`aliases` にあり、船が変わったらマイグレーションで直すことも 1 行で足す
- [X] T018 quickstart.md の「公開前に確かめる」を実行する（curl でタイトル・説明文・1行・「運行」の数が各ページ 2、375px 幅で横スクロールが出ない）。あわせて `SELECT scraper_class, ship_names, aliases FROM ferry_companies` で 2 社の値が data-model.md の表どおりで、他社の船が入っていないことを見る（FR-008）
- [X] T019 `make test-php`・`make phpstan`・`make cs-php`・`make lint-php`・`make verify-prod` を通してコミット

## Dependencies & Execution Order

- US1（Phase 3）は何にも依存しない。今のエンティティのままでできる
- US2（Phase 4）は US1 のあと。T011 は T001 で書き換えた description の後ろに足すため
- US2 の中は T008 → T009 → T010 → T011・T012 → T013。T014 は T009 のあとならいつでも
- Polish は US1・US2 のあと

## Parallel Example: User Story 1

```text
T001（company.html.twig）のあと、
T002（index.html.twig）と T003（ports.html.twig）は別のファイルなので同時にできる
```

## Parallel Example: User Story 2

```text
T009（FerryCompany.php）のあと、
T014（FerryCompanyTest.php）は T011・T012（company.html.twig）と同時にできる
```

## Implementation Strategy

1. **MVP = US1**：タイトル・説明文だけで、いちばん表示回数の多い会社ページの CTR に効く。DB を変えないので、先に公開して Search Console の数字を見始められる
2. **US2**：マイグレーションを入れて船の名前・別名を足す
3. **Polish**：18 の spec・CLAUDE.md に決定を残し、quickstart で確かめて公開する
