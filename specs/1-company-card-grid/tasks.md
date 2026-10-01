# Tasks: トップページ会社カード横並びグリッドレイアウト

**Input**: Design documents from `specs/1-company-card-grid/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: テストタスクを含む（[plan.md](plan.md) Step 4 / [research.md](research.md) R-005 でデグレード防止テストを明示的に要求しているため）

**Organization**: User Story 単位でフェーズを分割。各ストーリーは独立して実装・テスト・デリバリ可能。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 並行実行可（別ファイル・依存なし）
- **[Story]**: 対応する User Story（US1, US2, US3）
- ファイルパスは説明内に明記

## Path Conventions

Web application（Symfony MVP）構成。変更対象は `app/templates/` と `app/tests/` のみ。
`app/src/`・`scraper/`・`app/migrations/` は本機能で一切変更しない。

> **訂正（PR #16 レビュー）**: T001〜T017 のグリッド化タスクは上記の範囲で完結した。ただし末尾の「実装中に判明した事項」の既存不具合を
> 同じ PR で直したので、PR 全体では `app/src/DataFixtures`・`app/src/Entity`・`app/src/Repository`・`docker/mysql/init` も変更している。
> `scraper/`・`app/migrations/` は変更していない。

---

## Phase 1: Setup（環境準備）

**Purpose**: グリッドの検証に必要な複数会社データを用意する

- [X] T001 `make up` で Docker を起動し、`make fixtures` でテストデータを投入する。http://localhost:8080 を開き、変更前の状態（会社カードが縦積み）とスクロール量を確認しておく（変更後の SC-001 比較用）
- [X] T002 `app/src/DataFixtures/AppFixtures.php` を確認し、会社が3社未満の場合は phpMyAdmin（`make up-tools` → http://localhost:8081）で `ferry_companies` にダミー会社を追加して3社以上にする（3列グリッドの検証に必要）

**Checkpoint**: トップページに会社カードが3枚以上、縦積みで表示されている

---

## Phase 2: Foundational（ブロッキング前提）

**該当なし**。Bootstrap 5.3.3 は [app/templates/base.html.twig](../../app/templates/base.html.twig) で既に CDN 読み込み済み。
新規ライブラリ・CSSアセット・DBマイグレーション・Controller変更はいずれも不要（[research.md](research.md) R-001、[data-model.md](data-model.md)）。

---

## Phase 3: User Story 1 — 会社カードの横並び表示（Priority: P1）🎯 MVP

**Goal**: デスクトップで会社カードが1行に最大3社並び、表示順による視覚的な優劣がなくなる

**Independent Test**: 幅1200pxのブラウザでトップページを開き、会社カードが左右に3列並んで表示されることを目視確認できる

### Implementation for User Story 1

- [X] T003 [US1] `app/templates/status/index.html.twig` の `{% else %}`（`companies is empty` の偽側）直後に `<div class="row row-cols-lg-3 g-4">` を追加し、`{% endfor %}` の直後に対応する `</div>` を追加する。`{% if companies is empty %}` の alert は `row` の**外側**に残すこと（FR-006）
- [X] T004 [US1] `app/templates/status/index.html.twig` の `<div class="card mb-4">`（15行目付近）を `<div class="col">` + `<div class="card h-100">` の2重ラッパーに置き換える。`mb-4` は削除する（行間は `row` の `g-4` が担当するため残すと二重に空く）。カード末尾に対応する `</div>` を1つ追加し、`card-header` 以下のインデントを1段深くする
- [X] T005 [US1] `app/templates/status/index.html.twig` の `card-header`（会社名リンク・公式サイトリンク）と `ul.list-group`（航路名・ステータスバッジ6種・`航路情報がありません。`）を**一切変更していない**ことを `git diff` で確認する（FR-005）

### Tests for User Story 1

- [X] T006 [US1] `app/tests/Controller/StatusControllerTest.php` に `testIndexRendersCompanyGrid()` を追加する: `GET /` して `assertSelectorExists('.row.row-cols-lg-3')` でグリッドラッパーの存在を検証する
- [X] T007 [US1] `app/tests/Controller/StatusControllerTest.php` に `testCompanyCardsAreGridColumns()` を追加する: `GET /` して `.row > .col > .card.h-100` の構造を検証する。テストDBに会社データが無い場合はカード自体が描画されないため、`crawler.filter('.row .col')` の件数が0なら `markTestSkipped('会社データが無いためグリッド構造を検証できません')` とする（既存 `testCompanyPageReturns200WhenCompanyExists` と同じデータ非依存の方針）
- [X] T008 [US1] `make test-php` を実行し、既存4テスト + 新規2テストが全件パスすることを確認する

**Checkpoint**: 幅1200pxで3列表示になり、`make test-php` が green。この時点で **lg未満（992px未満）ではカードが1行に詰まって潰れる**（`.col` が等幅フレックスとして振る舞うため）。これは US2 で解消する

---

## Phase 4: User Story 2 — モバイルでの適切な折り返し表示（Priority: P2）

**Goal**: 狭い画面でカードが適切に折り返し、テキストと運航状況バッジが読み取れるサイズを維持する

**Independent Test**: デバイスエミュレーターで幅375pxに設定し、カードが1列で画面幅いっぱいに表示され、バッジが読める状態であることを確認できる

**Dependency**: Phase 3（US1）完了後。US1 が作った `row` に対してブレークポイントクラスを足す形になるため

### Implementation for User Story 2

- [X] T009 [US2] `app/templates/status/index.html.twig` のグリッドラッパーのクラスを `row row-cols-lg-3 g-4` から `row row-cols-1 row-cols-md-2 row-cols-lg-3 g-4` に変更する（`row-cols-1` = 768px未満で1列 / `row-cols-md-2` = 768〜991pxで2列 / `row-cols-lg-3` = 992px以上で3列）

### Tests for User Story 2

- [X] T010 [US2] `app/tests/Controller/StatusControllerTest.php` の `testIndexRendersCompanyGrid()` のアサーションを `assertSelectorExists('.row.row-cols-1.row-cols-md-2.row-cols-lg-3')` に更新し、3段階すべてのブレークポイントクラスが出力されることを検証する
- [X] T011 [US2] ブラウザの DevTools デバイスツールバー（`Cmd + Shift + M`）で **375px → 1列**・**800px → 2列**・**1200px → 3列** をそれぞれ目視確認する（FR-002〜FR-004 / SC-003）。375pxで会社名・航路名・ステータスバッジのテキストが読めることも併せて確認する

**Checkpoint**: 375 / 800 / 1200px の3幅すべてで意図した列数になり、レイアウト崩れがない

---

## Phase 5: User Story 3 — カード内コンテンツの維持（Priority: P3）

**Goal**: レイアウト変更によるデグレードが発生していないことを保証する

**Independent Test**: 変更後のトップページで、各カードの会社名・公式サイトリンク・航路名・運航状況バッジが変更前と同一であることを確認できる

**Dependency**: Phase 4（US2）完了後

### Tests for User Story 3

- [X] T012 [P] [US3] `app/tests/Controller/StatusControllerTest.php` に `testIndexKeepsCardContent()` を追加する: `GET /` して `.card .card-header` と `.card .list-group` の存在を検証する。会社データが0件の場合は `markTestSkipped` とする（FR-005 のデグレード検知）。**訂正（PR #16 レビュー）**: skip 方式はやめて、テスト内で会社データを作成・削除する方式に変更した
- [X] T013 [P] [US3] ブラウザで以下を目視確認する: 会社名リンクをクリックして `/company/{id}` に遷移する / 公式サイトリンクが別タブ（`target="_blank"`）で開く / 運航状況バッジ6種（通常運航・条件付遅延・欠航・運休・便なし・不明）の色とテキストが変更前と同一（FR-005）

### Edge Case Verification for User Story 3

- [X] T014 [US3] エッジケースを確認する（[quickstart.md](quickstart.md) セクション4）: 会社0件 → `現在情報がありません。` の alert が表示されレイアウト崩れなし（FR-006）／ 会社1社のみ → カード1枚が左寄せで表示され横に伸びきらない ／ 航路0件の会社 → カード内に `航路情報がありません。` が表示される

**Checkpoint**: デグレードなし。全エッジケースが期待どおり

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T015 `make test-php` を実行し、既存4テスト + 新規3テストの全件がパスすることを確認する。**訂正（PR #16 レビュー）**: レビュー対応で `testIndexShowsNoRouteMessageForCompanyWithoutRoutes` を追加したので、StatusControllerTest は既存4 + 新規4 = 8件になった。`make test-php` 全体（Repository テストを含む13件）が skip 0件でパスすることを確認済み
- [X] T016 `git diff app/templates/status/index.html.twig` を確認し、差分がグリッドラッパー（`row` / `col` / `h-100` / `mb-4`削除）に限定されていることをレビューする。カード内部の分岐ロジックに差分が出ていたら戻す（FR-005）
- [X] T017 ブラウザで変更前後の縦スクロール量を比較し、削減されていることを確認する（SC-001）。同一行のカード高さが揃っていること（航路数が違ってもカード下端が一直線）も併せて確認する（SC-004）

**Checkpoint**: 全 FR・SC を充足。コミット可能な状態

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1（Setup）**: 即開始可能
- **Phase 2（Foundational）**: 該当なし・スキップ
- **Phase 3（US1）**: Phase 1 完了後
- **Phase 4（US2）**: Phase 3 完了後（US1 が作成した `row` にクラスを追加するため）
- **Phase 5（US3）**: Phase 4 完了後（最終形に対するデグレード検証のため）
- **Phase 6（Polish）**: Phase 5 完了後

### User Story Dependencies

本機能は同一ファイル（`index.html.twig`）の同一箇所を段階的に育てる構造のため、
3ストーリーは **US1 → US2 → US3 の直列依存**。他機能でよくある「ストーリー間独立」は成立しない。

- **US1** 単体でもデスクトップでの価値（会社間の視覚的公平性 = 本機能の主目的）は提供される
- **US2** は US1 がモバイルで崩れるのを防ぐ必須の補完。US1 のみでリリースしてはいけない
- **US3** は実装タスクを持たない **検証専用フェーズ**

### Parallel Opportunities

- T012 と T013 は並行実行可（自動テストと目視確認で別作業）
- それ以外は同一ファイル（`index.html.twig` / `StatusControllerTest.php`）を触るため直列実行

---

## Implementation Strategy

### 推奨: US1 + US2 をまとめて1コミット

US1 単体はモバイルでレイアウトが崩れた状態のため、**リリース可能な最小単位は US1 + US2**。
Constitution V（フェーズごとのコミット）に従い、以下の単位でコミットする。

1. **コミット1**: Phase 3 + Phase 4（T003〜T011）— グリッド化 + レスポンシブ対応
2. **コミット2**: Phase 5 + Phase 6（T012〜T017）— デグレード検証テスト追加

### 最短経路（動くものを最速で見たい場合）

T003 → T004 → T009 の3タスクで見た目は完成する。テストと検証は後追いでも可。

---

## Notes

- 本機能の変更ファイル: `app/templates/status/index.html.twig`（実装）/ `app/tests/Controller/StatusControllerTest.php`（テスト）
- `app/templates/status/company.html.twig` は**対象外**。会社詳細ページのレイアウトは本機能のスコープに含まない
- DBマイグレーション・キャッシュクリア・アセットビルドはいずれも不要
- ロールバックは `git checkout -- app/templates/status/index.html.twig` で完了する
- ブレークポイントは Bootstrap 標準の `md`=768px / `lg`=992px（[research.md](research.md) R-002 で確定。spec 当初案の 600/900 から変更済み）

## 実装中に判明した事項（スコープ外・別途対応が必要）

実装の過程で以下が判明した。**4件とも対応済み**（1・2 は本機能のテストを成立させるために必要だったため同一コミット、3・4 は後続コミットで修正）。

1. **`AppFixtures` が空スタブだった** — `doctrine:fixtures:load` は実行前に全テーブルを purge するため、
   `make fixtures` を叩くと「DBを空にするだけ」のコマンドになっていた（実際に本作業中に dev DB のデータが消えた）。
   会社・航路・当日の運航状況を投入する実装に置き換えた（`app/src/DataFixtures/AppFixtures.php`）。
   ~~これによりテストDBにデータが入り、新規グリッドテストが skip されず実際にアサーションを実行するようになった。~~
   **訂正（PR #16 レビュー）**: `make fixtures` が投入するのは dev DB で、PHPUnit は `APP_ENV=test`（`_test` DB）を使う。
   そのためテスト DB が空だと新規グリッドテストは全件 skip されていた。
   `StatusControllerTest` 側で会社・航路・ステータスを作成し、終わったら削除する形に変更して、テストが常に実行されるようにした。

2. **`OperationStatus` に `#[ORM\HasLifecycleCallbacks]` が付いていなかった** — `#[ORM\PrePersist]` は定義されているが
   属性が無いため発火せず、PHP 側から永続化すると `created_at` が NOT NULL 違反で落ちる状態だった。
   スクレイパーは SQLAlchemy で直接書き込むため今まで露見していなかった。1 の fixtures 実装に必要なため属性を追加した。

3. **`docker/mysql/init/02_seed.sql` が現行スキーマで実行できない** — Doctrine マイグレーション後の
   `ferry_companies` / `routes` は `created_at` / `updated_at` に DEFAULT を持たないため、
   seed の INSERT が `Field 'created_at' doesn't have a default value` で失敗する。
   MySQL ボリューム初回作成時にしか実行されないため通常は表面化しないが、修正が必要だった。
   **対応済み**: 両 INSERT に `created_at` / `updated_at` を明示指定し、`ON DUPLICATE KEY UPDATE` にも `updated_at = NOW()` を追加。

4. **航路0件の会社はトップページに表示されない** — spec の Edge Cases は「`航路情報がありません。` が表示される」と
   記述しているが、[OperationStatusRepository::findTodayByAllCompanies()](../../app/src/Repository/OperationStatusRepository.php) は
   `join('fc.routes', 'r')` = INNER JOIN のため、航路を持たない会社はそもそも結果に含まれない。
   Twig 側の `{% else %} 航路情報がありません。` 分岐は index ページでは到達不能なデッドコードだった。
   **対応済み**: `leftJoin('fc.routes', 'r', 'WITH', 'r.active = :active')` に変更し spec の記述どおりの挙動にした。
   航路の絞り込みは WHERE ではなく WITH 句に置く必要がある（WHERE のままだと LEFT JOIN で NULL になった行が
   除外され INNER JOIN と同じ挙動に戻る）。回帰テスト2件を `OperationStatusRepositoryTest` に追加済み
   （INNER JOIN に戻すと両方 fail することを確認済み）。
