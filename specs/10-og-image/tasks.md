# Tasks: OG 画像を出す

**Input**: [spec.md](spec.md)・[plan.md](plan.md)・[research.md](research.md)・[data-model.md](data-model.md)・[contracts/head-meta.md](contracts/head-meta.md)・[quickstart.md](quickstart.md)
**Tests**: 書く（plan の Testing、research R8。既存テストの「og:image が 0 件」を書き換える必要がある）

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 別ファイルで依存が無く、並べて進められる
- **[Story]**: spec のユーザーストーリー（US1 だけ）

---

## Phase 1: Setup

Setup・Foundational は無し（新しい依存・DB の変更が無い。既存の `<head>` に足すだけ）。

---

## Phase 2: User Story 1 - シェアした URL が画像つきのカードで出る（Priority: P1）🎯 MVP

**Goal**: 全ページの `<head>` に OG 画像のタグを出し、1200×630 の画像を返す
**Independent Test**: `make test-php` が通り、`curl http://localhost:8080/ | grep og:image` で絶対 URL が出て、`curl -I http://localhost:8080/og-image.png` が 200・image/png

### 画像

- [X] T001 [P] [US1] 画像の元を `specs/10-og-image/og-image.html` に書く。1200×630、背景 #0073e6、`app/public/favicon.svg` の SVG をそのまま埋め込んだ船の絵（約 200px）、白い太字のサイト名「鹿児島〜沖縄フェリー運航情報」（約 64px、ヒラギノ角ゴ）、その下に小さく「マルエーフェリー・マリックスライン　運航状況を毎時更新」、下に白い波の線。文字・絵は端から 10% 以上内側（research R7、FR-002・003）。「ShipInfo」は入れない
- [X] T002 [US1] quickstart.md の「画像を作り直す」のコマンドで `app/public/og-image.png` を作り、目で確かめる（幅 300px に縮めてもサイト名が読めるか、SC-004）。PNG・1200×630・300KB 以下であること（FR-001・004）。depends on T001

### テスト（先に書いて落ちるのを確かめる）

- [X] T003 [P] [US1] `app/tests/Controller/StatusControllerTest.php` の `testHeadMetaOnAllPages` を書き換える：`twitter:card` = `summary_large_image`、`og:image` = `http://localhost/og-image.png`（テストのホスト。canonical と同じスキーム＋ホスト＋`/og-image.png` で比べる）、`og:image:type` = `image/png`、`og:image:width` = `1200`、`og:image:height` = `630`、`og:image:alt` = `鹿児島〜沖縄フェリー運航情報 - 青地にフェリーの絵とサイト名`（contracts/head-meta.md）
- [X] T004 [P] [US1] `app/tests/Controller/StatusControllerTest.php` に画像ファイルのテストを足す：`public/og-image.png`（`kernel.project_dir` から組み立てる）を `getimagesize()` で読み、1200×630・`IMAGETYPE_PNG`、`filesize()` が 300 * 1024 以下（SC-002）
- [X] T005 [P] [US1] `app/tests/Controller/ErrorPageTest.php` の `testNotFoundPageHeadMeta` で、404 のページにも `og:image`・`og:image:type`・`og:image:width`・`og:image:height`・`og:image:alt` が 1 件ずつあり、`twitter:card` が `summary_large_image` であることを確かめる

### 実装

- [X] T006 [US1] `app/config/packages/twig.yaml` の globals に `og_image_alt: '鹿児島〜沖縄フェリー運航情報 - 青地にフェリーの絵とサイト名'` を足す（data-model.md）
- [X] T007 [US1] `app/templates/base.html.twig` の `og:site_name` の後に `og:image`（`{{ app.request.schemeAndHttpHost }}/og-image.png`）・`og:image:type`・`og:image:width`・`og:image:height`・`og:image:alt`（`{{ og_image_alt }}`）を足し、`twitter:card` を `summary_large_image` にする。上のコメントに og:image もリクエストのホストを使う旨を足す（research R4・R5）。depends on T006
- [X] T008 [US1] `make test-php`・`make lint-php`・`make phpstan`・`make cs-php` を通す。ローカルで quickstart.md の「3. ローカルで確かめる」の curl 2 本を確かめる

**Checkpoint**: コミット `feat(app): 全ページに OG 画像を出す (10-og-image implement)`

---

## Phase 3: Polish

- [X] T009 [P] `CLAUDE.md` の「重要な設計決定」のサイト名・OG の行に「OG 画像は全ページ共通の `app/public/og-image.png`（元は `specs/10-og-image/og-image.html`）」を足す
- [ ] T010 本番に出した後、quickstart.md の「4. 本番で確かめる」を行う（SC-003。PR マージ後に手で行う）

**Checkpoint**: コミット `docs: OG 画像の置き場所を CLAUDE.md に書く (10-og-image polish)`

---

## Dependencies & Execution Order

- T001 → T002（画像の元 → PNG）
- T003・T004・T005 は T001・T002 と並べて書ける（T004 は T002 の後に通る）
- T006 → T007 → T008
- T009 はいつでも。T010 はマージ・デプロイの後

### Parallel Example

```text
T001（画像の元）・T003（head のテスト）・T005（エラーページのテスト）を同時に進める
```

## Implementation Strategy

US1 だけの 1 PR。T001〜T008 でテストまで通ったら 1 コミット、T009 で 1 コミット。T010 はデプロイ後に確認する。
