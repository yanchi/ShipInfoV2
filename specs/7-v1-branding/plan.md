# Implementation Plan: V1 の見た目・ファビコン・OG を引き継ぐ

**Branch**: `7-v1-branding` | **Date**: 2026-10-05 | **Spec**: [spec.md](spec.md)

---

## Summary

V2 の画面の構成・機能はそのままに、見た目とサイトの名乗り方を V1（`../ShipInfo`）にそろえる。DB・スクレイパー・既存のルートの振る舞いは変えない。

- **`<head>`**：ページごとの title・description と、canonical・OG・Twitter カードを `base.html.twig` のブロックで組み立てる。サイト名などの固定文言は Twig グローバルに置く
- **テイスト**：Bootstrap 5.3 は残し、CSS 変数の上書きと少量の自前 CSS で V1 の青いヘッダー・グレーの背景・白い角丸カード・青い下線の見出し・V1 配色のバッジ・濃いグレーのフッターにする。CSS は `_site_styles.html.twig` に切り出す
- **ファビコン**：V1 の `favicon.svg` を `public/` にコピー（V1 と同じ URL）
- **V1 の URL・検索エンジン**：`/details/today` を `/ports` へ 301。`/robots.txt`・`/sitemap.xml` を Symfony のルートで返す
- **GA**：V1 と同じく、本番かつ `GOOGLE_ANALYTICS_ID` があるときだけ gtag.js を出す
- **エラーページ**：TwigBundle のエラーテンプレートを上書きし、DB を読まない形でヘッダー・フッター・ファビコンを出す

---

## Technical Context

**Language/Version**: PHP 8.3
**Primary Dependencies**: Symfony 7.4（FrameworkBundle の `RedirectController`、TwigBundle のエラーテンプレート）、Twig、Bootstrap 5.3（CDN、読み込み済み）。新しい依存は無い
**Storage**: MySQL 8.0。変更なし（sitemap で既存の `FerryCompanyRepository::findActive()` を読むだけ）
**Testing**: PHPUnit（Controller の機能テスト。エラーページは `createClient(['debug' => false])`）
**Target Platform**: Docker Compose（開発）、さくら VPS の `compose.prod.yml`（本番）
**Project Type**: Web アプリ（MVP、Twig）
**Performance Goals**: リクエストあたりの DB クエリは増やさない（`/sitemap.xml` は会社一覧の1本だけ）。CSS はインラインのまま（追加のリクエストはファビコンの1本だけ、nginx が静的に返す）
**Constraints**:
- 画面の構成・機能・ルートの振る舞いを変えない（FR-020、SC-006）。既存テストのうち、見た目のクラス（`.badge.bg-success`）と「ShipInfo」を見ている箇所だけ書き換える
- 375px〜1280px 以上で横スクロールなし。ナビは 375px でも1行
- ダークモードでも明るい配色
- エラーページは DB を読まない（DB 障害時の 500 でも描画できるように）
- GA は本番かつ ID があるときだけ。ローカル・CI では外部に何も送らない
**Scale/Scope**: 3ページ＋エラーページ＋4ルート（`/favicon.svg` は静的）

未解決の NEEDS CLARIFICATION は無い（[research.md](research.md) で全部解決済み）。

---

## Constitution Check

| Gate | Status | 備考 |
|---|---|---|
| I. スクレイパー優先設計 | ✅ PASS | スクレイパーは変更しない |
| II. Twig + Controller、API なし | ✅ PASS | Twig のテンプレートと、`robots.txt`・`sitemap.xml` を返す Controller を足すだけ。API は作らない |
| III. データ品質・キーごとの最新状態 | ✅ PASS | DB を変えない。読み取りのみ |
| IV. Docker で完結 | ✅ PASS | 追加の環境は無い。GA の ID は `compose.prod.yml` の環境変数で渡す |
| V. フェーズごとにコミット・スコープを制限 | ✅ PASS | 下の PR1・PR2 に分け、tasks.md のグループごとにコミットする |
| 技術スタック（変更禁止） | ✅ PASS | 依存の追加なし |

**Phase 1 設計の後に再チェック**: 違反は無し。

---

## Project Structure

### Documentation

```
specs/7-v1-branding/
├── spec.md
├── research.md
├── data-model.md
├── contracts/
│   ├── http-routes.md
│   └── ui-theme.md
├── quickstart.md
├── plan.md          ← このファイル
└── tasks.md         （/speckit.tasks で生成）
```

### 変更対象

```
app/public/favicon.svg                                   # 新規：V1 からコピー
app/config/packages/twig.yaml                            # globals（site_name・site_top_title・title_suffix・og_site_name・copyright・ga_measurement_id）
app/config/routes.yaml                                   # /details/today → app_status_ports（301）
app/src/Controller/SeoController.php                     # 新規：/robots.txt・/sitemap.xml

app/templates/base.html.twig                             # <head> のメタ情報・GA、V1 のヘッダー・フッター、DB を読む部分をブロックに
app/templates/_site_styles.html.twig                     # 新規：共通 CSS（base の <style> から移し、V1 のテイストを足す）
app/templates/status/_status_badge.html.twig             # V1 配色のクラスに
app/templates/status/_status_warning.html.twig           # 新規：V1 の注意書き
app/templates/status/_port_entry.html.twig               # 注意書きを出す
app/templates/status/index.html.twig                     # title・description、h1、注意書き、.no-data、注記の <footer> → <p>
app/templates/status/ports.html.twig                     # title・description、.no-data、注記の <footer> → <p>
app/templates/status/company.html.twig                   # title・description、注意書き、注記の <footer> → <p>
app/templates/seo/sitemap.xml.twig                       # 新規
app/templates/bundles/TwigBundle/Exception/error.html.twig     # 新規
app/templates/bundles/TwigBundle/Exception/error404.html.twig  # 新規

app/tests/Controller/StatusControllerTest.php            # <head>・ヘッダー・フッター・バッジ・注意書きのテスト。既存の .badge.bg-success・'ShipInfo' を書き換え
app/tests/Controller/SeoControllerTest.php               # 新規：robots・sitemap・/details/today
app/tests/Controller/ErrorPageTest.php                   # 新規：404 のエラーページ

compose.prod.yml                                         # app に GOOGLE_ANALYTICS_ID を渡す
deploy/.env.production.example                          # GOOGLE_ANALYTICS_ID を追加（空）
deploy/README.md                                         # 切り替え手順に GA の ID と確認項目を追記
CLAUDE.md                                                # 「重要な設計決定」の V1 引き継ぎ（サイト名・GA の ID の入れ方）を1行
```

**Structure Decision**: 既存の Controller + Twig の構成に合わせる。`robots.txt`・`sitemap.xml` は運航情報とは関心が違うので、`StatusController` に足さず `SeoController` に分ける。CSS はアセットのビルド環境を入れないので、テンプレートのパーシャルとしてインラインに置く（research R1）。

---

## 実装の分割（PR）

| PR | 範囲 | spec | 主な変更 |
|---|---|---|---|
| **PR1** | 見た目・ファビコン・`<head>`・エラーページ | US1・US2（FR-001〜016、FR-020） | `favicon.svg`、`twig.yaml` の globals（GA 以外）、`base.html.twig`、`_site_styles`、`_status_badge`・`_status_warning`・`_port_entry`、3ページのテンプレート、エラーテンプレート、テスト |
| **PR2** | V1 の URL・検索エンジン・GA・切り替え手順 | US3（FR-017〜019）、FR-021・022 | `routes.yaml`、`SeoController`・`sitemap.xml.twig`、`ga_measurement_id` と gtag、`compose.prod.yml`・`.env.production.example`・`deploy/README.md`、テスト |

PR2 は PR1 の `base.html.twig` に GA のタグを足すので PR1 の後。どちらも単独で本番に出して問題ない（PR1 だけでも V1 と同じ見た目になり、PR2 は切り替えの前に入っていればよい）。

---

## 主な設計判断（詳細は research.md）

| 判断 | 内容 | research |
|---|---|---|
| CSS | Bootstrap は残し、CSS 変数の上書き＋自前 CSS。インラインのパーシャルに切り出す | R1 |
| ダークモード | `data-bs-theme="light"`・`color-scheme: light` で固定 | R2 |
| バッジ | V1 配色の `status-badge--{状態}`。記号・文言は 5-ui-readability のまま。寄港地変更・スケジュール変更は V2 にステータスが無いので作らない | R3 |
| 異常の行 | 線・薄い背景・太字は保ち、色を V1 の系統に | R4 |
| 注意書き | 欠航・条件付・遅延の便・航路に、V1 と同じ赤い小さな文字で | R5 |
| `<head>` | `title`・`full_title`・`description` のブロック。canonical・og:url はリクエストのスキーム+ホスト+パス | R6 |
| エラーページ | TwigBundle のテンプレートを上書き。DB を読む部品はブロックにして外す | R7 |
| `/details/today` | `RedirectController` で `/ports` に 301 | R8 |
| robots・sitemap | `SeoController` のルート。ホストはリクエストのもの | R9 |
| GA | V1 と同じ。`GOOGLE_ANALYTICS_ID` は切り替えのときに VPS の `.env.production` に入れる | R10 |
| ヘッダー | サイト名は h1 にせず中央、ナビは1行。サイト名は決めた境目でだけ折り返す | R12 |
| トップの h1 | 「現在の運航状況」に変える | R13 |

## Complexity Tracking

違反は無いので記載なし。
