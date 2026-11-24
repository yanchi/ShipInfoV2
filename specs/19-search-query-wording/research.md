# Research: 検索語に合わせた会社ページの説明文と船の名前

## R1. 船の名前・別名をどこに置くか

- **Decision**: `ferry_companies` に `ship_names`・`aliases`（どちらも JSON の文字列の配列、NULL 可）を足し、マイグレーションで 2 社の値を入れる。行は `scraper_class`（`MarueFerry`・`MarixLine`）で探す
- **Rationale**: 会社の属性なので会社の行に置くのが素直。18 で港の呼び名（`ports.display_name`）を DB に置いたのと同じやり方で、本番にもマイグレーションで入る。`scraper_class` はスクレイパーの登録名で、会社名より変わりにくい
- **Alternatives considered**:
  - twig.yaml の globals に会社 id ごとに書く → 設定が DB の id に依存する。テストの会社（id が毎回違う）で確かめにくい
  - PHP の定数（会社名や `scraper_class` をキーにした配列）→ 動くが、会社の情報が DB とコードに分かれる
  - 便データ（`departure_statuses.ship_name`）から拾う → spec の Clarification で不採用

## R2. 列を NULL 可にする理由

- **Decision**: `ship_names`・`aliases` は NULL 可。エンティティの getter は NULL を空の配列として返す
- **Rationale**: スクレイパーのテスト（`scraper/tests/conftest.py` など）が SQLAlchemy で `ferry_companies` に行を入れている。NOT NULL にすると、JSON 列は MySQL で文字の既定値を持てないので、スクレイパー側のモデルやテストも直す必要が出る（Constitution I：スクレイパーに影響させない）。NULL 可ならスクレイパーは何も変えなくてよい。`make check-schema` は「スクレイパーのモデルの列が DB にあるか」を見るだけなので、DB の列が増えても通る
- **Alternatives considered**: `NOT NULL DEFAULT (JSON_ARRAY())`（MySQL 8.0.13 以降の式の既定値）→ Doctrine の `schema:validate`（`make lint-php`）で差分が出やすい

## R3. タイトルの形

- **Decision**: `<会社名> 運航状況 リアルタイム（今日・明日）` + suffix
- **Rationale**: 検索結果のタイトルは日本語で 30 文字前後で切れる。「マリックスライン 運航状況 リアルタイム（今日・明日）」は 27 文字で、切れても全部残る。CTR の高いクエリ（「リアルタイム」6.75%、「明日」14%）の語を前半に入れる
- **Alternatives considered**: 「【リアルタイム】マリックスライン 運航状況…」→ 先頭が会社名でなくなり FR-001 に合わない。会社名で探す人に一致が見えにくい

## R4. 説明文の形と「運行」の入れ方

- **Decision**: 会社ページは `<会社名>の運航（運行）状況をリアルタイムで。今日・明日の欠航・遅延を毎時更新し、今日から4日分を航路ごとにまとめて確認できます。運航船：<船の名前を「・」でつなぐ>。`（船の名前が無ければ最後の文を出さない）。トップ・港別・港のページは、今の説明文の「運航状況」1 か所を「運航（運行）状況」にする
- **Rationale**: スマホの検索結果で出るのは 50〜60 文字くらい。会社名・「運航（運行）状況」・リアルタイム・今日・明日を最初の 40 文字に入れ、船の名前は後ろに置く（spec の Edge Cases）。「運航（運行）」は括弧書きなので、読み方の補足として自然に読める
- **Alternatives considered**: 「運航・運行状況」→ 同じ意味の語を並べたように見えて不自然

## R5. 本文の1行の形

- **Decision**: h1 の行のすぐ下に `<p class="small text-muted">` で `運航船：フェリー波之上・フェリーあけぼの ／ 別名：Aライン（エーライン）`。船の名前だけ・別名だけのときは、ある方だけ出す。両方無ければ `<p>` ごと出さない
- **Rationale**: spec の Clarification（h1 のすぐ下に小さい1行）。「別名：」を付けると、どれが船でどれが会社の呼び方か読んで分かる（spec の Clarification の例もこの形にそろえた）。別名は表示用の文字列（「Aライン（エーライン）」）として持ち、表記ゆれの注記もデータ側で決める

## R6. 既存テストへの影響

- **Decision**: `StatusControllerTest::testNoUnkoSpellingOnAnyPage` を「レスポンスから meta description と og:description の 2 つのタグを除くと『運行』が無い」「description に『運航（運行）状況』がちょうど 1 回ある」に書き換える。`testTopTitleAndDescription`・`testPageTitleFormat`・`testOgTagsAreNotDoubleEscaped` の期待値を新しいタイトル・説明文に直す
- **Rationale**: 18 の SC-005（どのページにも「運行」が無い）を、19 の FR-004（description にだけ出す）に置き換えるため

## R7. 関連ドキュメント

- **Decision**: `specs/18-port-seo-pages/spec.md` の Clarifications に「19 で description だけ変えた」と追記する。`CLAUDE.md` の「タイトル・説明文は 18-port-seo-pages で検索向けにした」の行に 19 のことを足す
- **Rationale**: 18 で決めたことを 19 で変えたと分かるようにする（18 が 7-v1-branding に追記したのと同じ）
