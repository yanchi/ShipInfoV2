# Research: 港ごとのページと、検索で選ばれるタイトル・説明文

## R1. 港の URL の名前（slug）をどこに持つか

- **Decision**: `ports` テーブルに `slug`（`VARCHAR(32) NOT NULL UNIQUE`）を足し、マイグレーションで 7 港に値を入れる
- **Rationale**: 港はマイグレーション（`Version20261001000000`）でだけ作られ、スクレイパーは読むだけ（`scraper/scraper/db/models.py` の `Port` に書き込みは無い）。だから NOT NULL の列を足しても、スクレイパーを変えずに済む。港を足すときもマイグレーションで `name` と一緒に入れればよく、「港が増えたのに URL が無い」状態が起きない。表示名（`name`）と別の列なので、表示名を直しても URL は変わらない（spec の Edge Cases）
- **Alternatives considered**:
  - PHP の定数（港名 => slug の対応表）: 港名を直すと対応が切れる。DB と二重管理になる
  - 港名を自動でローマ字にする: 「和泊（わどまり）」「本部（もとぶ）」など読みを機械で決められない
- `make check-schema` はスクレイパーのモデルの列が DB にあるかを見るので、DB 側に列を足すだけなら影響しない。スクレイパーのモデルには足さない（使わない）

## R2. 港の呼び名（「徳之島（亀徳港）」）をどう作るか

- **Decision**: `ports` に `display_name`（`VARCHAR(64) NULL`）を足して、呼び名をそのまま入れる。NULL なら `name` を使う（`Port::getDisplayName()`）
  - 名瀬 → `奄美大島（名瀬港）`、亀徳 → `徳之島（亀徳港）`、和泊 → `沖永良部島（和泊港）`、与論 → `与論島（与論港）`、本部 → `沖縄・本部港`、鹿児島・那覇 → NULL
- **Rationale**: spec の FR-004 には「島の港は `<島>（<港>港）`」という決まりと、本部（沖縄・本部港）という例外がある。島の名前だけを持って組み立てると、例外のための分岐が要る。呼び名をそのまま持てば分岐が要らない。spec の Key Entities は「島の名前」と書いているけど、ほしいのは呼び名なので、こちらの持ち方にする（data-model.md）
- **Alternatives considered**: `island_name` 列＋組み立てのロジック。本部の例外を表せない

## R3. ルートと、`/ports/filter` との関係

- **Decision**: `GET /ports/{slug}`（ルート名 `app_status_port`、`requirements: ['slug' => '[a-z][a-z0-9-]*']`）。slug に合う港が出発港の一覧に無ければ 404
- **Rationale**: `POST /ports/filter` とは HTTP メソッドが違うので、ぶつからない。`GET /ports/filter` は slug が `filter` の港として探され、無いので 404 になる（今も GET /ports/filter は 405 で、どちらでも画面には出ない）。出発港の一覧（`RouteStopRepository::findBoardStops()`）で判定するのは、絞り込みで選べる港と同じにするため。到着しかしない港や、使われなくなった港を出さない
- **Alternatives considered**: `/port/{slug}`・`/ports/{id}`: 前者は今の `/ports` と別物に見える。後者は spec の FR-001（内部番号を出さない）に反する

## R4. 港のページと Cookie（保存した港）

- **Decision**: `PortFilterResolver` に `resolveForPort(Request, boardStops, Port)` を足す。港は URL のもの、方向は `dir` クエリ（不正なら両方向）、`hasSaved` は Cookie があるか。Cookie が不正なら今までどおり消す。Cookie は書かない
- **Rationale**: 今の `/ports?port=5` と同じ扱い（URL が優先・Cookie は読むだけ）で、spec の FR-010 を満たす。Cookie の中身は `port=<id>&dir=` のままにする。slug に変えると、今保存している人の Cookie が不正扱いになって消えてしまう（FR-009）
- レスポンスは今の `/ports` と同じく `Cache-Control: private`・`Vary: Cookie`（「保存を解除」を出すかが Cookie で変わる）

## R5. 古い URL（`/ports?port=<id>`）の転送

- **Decision**: `GET /ports` で `port` が出発港の一覧にある港の ID なら、`/ports/{slug}`（`dir` が正しければ `?dir=` を付ける）へ **301**。`port=all`・不正な番号・`port` 無しは今までどおり表示する
- **Rationale**: 検索エンジンとブックマークの両方を新しい URL に移すには 301 が合う。港の ID と slug の対応は変わらないので、ブラウザが 301 を覚えても困らない。不正な `dir`（例: `?port=3&dir=xx`）は捨てて転送する（今も不正な dir は両方向として表示している）
- `PortFilterResolver::resolve()` の結果に「転送先」を足す（`PortFilterResolution::$redirectTo` は今 POST 用に使っているので、GET でも使う）

## R6. フォーム（POST /ports/filter）の移り先

- **Decision**: `PortFilterResolver::url()` を、港があれば `/ports/{slug}`（＋`?dir=`）、港が無ければ今までどおり `/ports?dir=…` か `/ports?port=all` にする。303 のまま
- **Rationale**: 古い形に飛ばしてから 301 でもう一度飛ぶと、リダイレクトが 2 回になる。`url()` は Port を引ける（`departurePorts()` の結果に slug がある）

## R7. 検索エンジンがたどれるリンク

- **Decision**: 港別ページ（全港・各港）に「港ごとのページ」として 7 港へのリンクを並べる（`<nav aria-label="港ごとのページ">`）。リンクの文字は港の呼び名（`getDisplayName()`）にする。リンクの文字は検索エンジンがリンク先を理解する手がかりで、「亀徳」だけでは「徳之島」と結びつかないため（短い島名用の列を別に足すより、呼び名を使い回すほうが単純）。いま見ている港は `<span aria-current="page">` にする。トップの「4日分を見る」は、保存した港があればその港のページへのリンクにする
- **Rationale**: 今の絞り込みは POST のフォームなので、クローラーは港のページへたどれない。sitemap だけより、サイトの中のリンクもあるほうが早く・確実にインデックスされる。ヘッダーのナビには足さない（spec の Out of Scope）
- ヘッダーの「港別」は、`app_status_ports` と `app_status_port` の両方で「いまいるページ」として示す（FR-013b）

## R8. タイトル・説明文の文言

- **Decision**（`app/config/packages/twig.yaml` の globals とテンプレート）:
  - `site_top_title`: `鹿児島〜奄美・沖縄 フェリー運航状況（今日・明日）| 欠航・遅延をリアルタイム確認`
  - `title_suffix`: ` | 鹿児島〜奄美・沖縄フェリー運航情報`
  - 港別（全港）: `港別 フェリー運航状況（今日・明日）` + suffix
  - 港のページ: `<呼び名>発 フェリー運航状況（今日・明日）` + suffix
  - 会社別: `<会社名> 運航状況（今日・明日）` + suffix
  - 説明文は contracts/seo-meta.md
- **Rationale**: 検索結果のタイトルは日本語で 30 文字前後で切れる。だから、港名・会社名と「運航状況（今日・明日）」を先頭に置く。suffix には「奄美」を入れる（「鹿児島-奄美 フェリー」で検索されている）。「運行」は使わない（spec の Clarifications）
- `site_name`（ヘッダー）・`og_site_name`・`copyright` は変えない（FR-020）
- 大見出しは、港のページを `<呼び名>発の運航状況` にする。全港・トップ・会社別は今のまま
- エラーページ（404 など）のタイトルも suffix を使うので、suffix が変わればいっしょに変わる（`ErrorPageTest` を直す）

## R9. sitemap

- **Decision**: `SeoController::sitemap()` に、出発港の一覧の港ごとに `/ports/{slug}`（priority `0.9`）を足す。順番は出発港の一覧の順（下りの寄港順）
- **Rationale**: 港のページは「港別」と同じくらい大事。港の判定は R3 と同じ出発港の一覧を使う
