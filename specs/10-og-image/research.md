# Research: OG 画像を出す

## R1. 画像の形式

- **Decision**: PNG（1200×630）
- **Rationale**: 単色の背景と文字・図形だけの画像なので、PNG の方が文字の縁がにじまず、ファイルも小さい（数十 KB の見込み。FR-004 の 300KB に十分収まる）。LINE・X・Slack・Facebook とも PNG を表示できる
- **Alternatives considered**: JPEG（写真向き。文字の周りにノイズが出る）、SVG（多くの SNS が og:image として表示しない）、WebP（古いクローラーが読めないことがある）

## R2. 画像の作り方

- **Decision**: 画像の元を HTML（`specs/10-og-image/og-image.html`、ファビコンの SVG をそのまま埋め込む）で書き、ヘッドレス Chrome のスクリーンショットで 1200×630 の PNG にして `app/public/og-image.png` に置く。PNG はリポジトリに入れ、実行時には作らない
- **Rationale**: ファビコンの船の絵を同じ SVG のまま使えるので、絵がずれない。日本語の文字をきれいに描ける書体（ヒラギノ角ゴ）が使える。作り直すときは同じ HTML から同じ手順で作れる（手順は quickstart.md）
- **Alternatives considered**:
  - Pillow で描く：日本語の書体を Docker のイメージに入れる必要があり、SVG の船の絵を描き直すことになる
  - 実行時に画像を作る（GD・Imagick など）：全ページ共通の 1 枚なので不要。依存も増える（Out of Scope）
- **Constitution IV（Docker 完結）との関係**: 画像を作り直すときだけ開発者の Chrome を使う。アプリの起動・テスト・ビルドには Chrome も画像を作る手順も要らない（PNG がリポジトリにある）ので、開発環境のホスト依存は増えない

## R3. 画像の置き場所と URL

- **Decision**: `app/public/og-image.png`。URL は `/og-image.png`
- **Rationale**: `favicon.svg` と同じく `public/` の直下に置けば、開発（`docker/nginx`）も本番（`docker/production/app/nginx.conf`、`COPY app/ .`）も nginx が静的に返す。ルートや Controller は要らない
- **Alternatives considered**: AssetMapper・バージョンつきのファイル名：アセットのビルドの仕組みを入れていない（7-v1-branding R1）ので使わない。画像を差し替えたときに SNS のキャッシュを避けたければ、ファイル名を変える（Out of Scope）

## R4. og:image の値（絶対 URL）

- **Decision**: `app.request.schemeAndHttpHost ~ '/og-image.png'`
- **Rationale**: og:url・canonical と同じ式で、ローカル・v2 のホストでは自分のホストを指す（spec の Edge Cases）。本番は trusted_proxies の設定済みで `https` になる
- **Alternatives considered**: 本番の URL を固定で書く：ローカルで本番を指してしまう（7-v1-branding FR-019 と同じ理由で採らない）

## R5. head に出すタグ

- **Decision**: `og:image`・`og:image:type`（image/png）・`og:image:width`（1200）・`og:image:height`（630）・`og:image:alt`、`twitter:card` を `summary_large_image` に。`twitter:image` は出さない
- **Rationale**: width・height があると Facebook などが画像を取りに行く前にカードを組める。X は `twitter:image` が無ければ `og:image` を使う。type は 1 行で済み、クローラーの判定を助ける
- **Alternatives considered**: `og:image:secure_url`：og:image がすでに https なので不要

## R6. 文言・寸法の置き場所

- **Decision**: alt の文言は `twig.yaml` の globals（`og_image_alt`）に置く。画像のパス・寸法・形式は `base.html.twig` に直接書く
- **Rationale**: サイトの文言は globals に集める決まり（CLAUDE.md「サイト名・タイトル・OG の文言は twig.yaml の globals」）。パス・寸法は画像ファイルと 1 対 1 で、ほかから使わないので、テンプレートに書いた方が読みやすい
- **alt の文言**: 「鹿児島〜沖縄フェリー運航情報 - 青地にフェリーの絵とサイト名」

## R7. 画像の見た目

- **Decision**: 背景は V1 のヘッダーの青（#0073e6）。中央に、ファビコンの船の絵（白い角丸の枠の中、約 200px）と、白い太字のサイト名「鹿児島〜沖縄フェリー運航情報」（約 72px）、その下に小さく「Aライン・マリックスライン　運航状況を毎時更新」。下に白い波の線。文字と絵は上下左右の端から 10% 以上内側（FR-003）
- **Rationale**: ヘッダーと同じ青地に白い文字で、サイトを開いたときの見た目とつながる。72px のサイト名は、幅 300px に縮めても約 18px になり読める（SC-004）

## R8. テスト

- **Decision**: `StatusControllerTest::testHeadMetaOnAllPages` の「og:image が 0 件」を、og:image（= `http://localhost/og-image.png`、テストのホスト）・width・height・alt・type と `summary_large_image` を確かめる形に書き換える。`ErrorPageTest` にも og:image の各タグを足す。画像ファイルそのものは PHPUnit で `getimagesize()` を使い、1200×630・PNG・300KB 以下を確かめる
- **Rationale**: 画像を差し替えたときに寸法や大きさを間違えても CI で気づける（SC-002）
