# Data Model: V1 の見た目・ファビコン・OG を引き継ぐ

**Feature**: [spec.md](spec.md) | **Date**: 2026-10-05

**DB は変えない**。エンティティ・マイグレーション・スクレイパーの変更は無い。
この機能で増えるのは、テンプレートで使う固定値（Twig のグローバル変数）と、ページごとのメタ情報（Twig のブロック）だけ。

---

## サイトの固定値（Twig グローバル）

`config/packages/twig.yaml` の `twig.globals`。全テンプレートとテストで同じ値を使う。

| 名前 | 値 | 使う場所 |
|---|---|---|
| `site_name` | `鹿児島〜沖縄・奄美大島 フェリー運航情報` | ヘッダーのサイト名 |
| `site_top_title` | `鹿児島〜沖縄・奄美大島フェリー運航情報` | トップの `<title>`（V1 のトップと同じ。`site_name` と違い空白が無い） |
| `title_suffix` | ` \| 鹿児島〜沖縄フェリー運航状況` | トップ以外の `<title>` の後ろ |
| `og_site_name` | `鹿児島〜沖縄フェリー運航情報サービス` | `og:site_name` |
| `copyright` | `© 2025 鹿児島〜沖縄・奄美大島 フェリー運航情報サービス` | フッター |
| `ga_measurement_id` | `%env(default::GOOGLE_ANALYTICS_ID)%` | GA のタグ（空なら出さない） |

文言は V1 のテンプレートからそのまま写す（spec の Assumptions：V1 のリポジトリの現状を正とする）。

---

## ページのメタ情報（Twig ブロック）

`base.html.twig` が持つブロック。`<head>` の各項目はこのブロックから組み立てる（research R6）。

| ブロック | 中身 | 既定 |
|---|---|---|
| `title` | ページ名 | 無し（各ページで必須） |
| `full_title` | `<title>`・`og:title` の値 | `{{ block('title') }}{{ title_suffix }}` |
| `description` | `<meta name="description">`・`og:description` の値 | サイト共通の説明文（下表の「既定」） |

`canonical`・`og:url` はブロックにせず、`app.request.schemeAndHttpHost ~ app.request.pathInfo` で全ページ同じ式にする。

### ページごとの値

| ページ | `title` | `full_title` | `description` |
|---|---|---|---|
| トップ `/` | 現在の運航状況 | `{{ site_top_title }}` | Aライン・マリックスラインの鹿児島〜那覇・奄美大島間フェリーの最新運航状況。欠航・遅延情報を毎時更新。旅行前に出発港・到着港の運航状況をご確認ください。（V1 のトップと同じ） |
| 港別 `/ports` | 港別運航情報 | 既定 | 鹿児島〜那覇・奄美大島間の各港を出るフェリーの出港時刻と運航状況。Aライン・マリックスラインの今日から4日分の欠航・遅延情報を港ごとに確認できます。 |
| 会社別 `/company/{id}` | `{{ company.name }} 運航状況` | 既定 | `{{ company.name }}`の鹿児島〜那覇・奄美大島間フェリーの運航状況。今日から4日分の航路ごとの欠航・遅延情報と出港時刻を確認できます。 |
| エラー（404） | ページが見つかりません | 既定 | 既定 |
| エラー（その他） | エラーが発生しました | 既定 | 既定 |
| 既定（上書きしないページ） | — | — | 鹿児島〜沖縄・奄美大島を結ぶAライン・マリックスラインのリアルタイム運航状況。欠航・遅延・通常運航を毎時更新でお知らせします。（V1 の base の既定と同じ） |

- 説明文の「毎時更新」は V1 の文言を引き継ぐ（V2 のスクレイパーの間隔は 30 分なので事実と矛盾しない）
- 会社名は DB の `ferry_companies.name` をそのまま使う（Twig の自動エスケープで属性値に入れる）

---

## ステータスと表示の対応

5-ui-readability の [contracts/ui-status.md](../5-ui-readability/contracts/ui-status.md) の記号・文言は変えない。見た目だけを [contracts/ui-theme.md](contracts/ui-theme.md) の「ステータスのバッジ」に置き換える。

V1 の注意書き（FR-016）を出す状態：

| `OperationStatusEnum` | 注意書き |
|---|---|
| `cancelled` | 出す |
| `delayed` | 出す |
| `operating`・`suspended`・`unknown`・`no_service`・null | 出さない |

`DepartureDisplayStateEnum` が `status` 以外（運航予定・情報なし・便なし）のときは出さない（research R5）。
