# Implementation Plan: 港ごとのページと、検索で選ばれるタイトル・説明文

**Branch**: `18-port-seo-pages` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/18-port-seo-pages/spec.md`

## Summary

出発港ごとに `GET /ports/{slug}` のページを足す。港別ページの絞り込みを 1 港に固定した内容で、港の呼び名入りのタイトル・h1・説明文を付け、sitemap と港別ページ内のリンクから検索エンジンがたどれるようにする。
古い `/ports?port=<id>` は 301 で、フォームの移り先は 303 で新しい URL に向ける。Cookie（保存した港）の形式と動きは変えない。
あわせて、トップ・港別・会社別のタイトルと説明文に「今日・明日」「欠航・遅延」「リアルタイム／毎時更新」を入れる。表記は「運航」のまま。

## Technical Context

**Language/Version**: PHP 8.3（Symfony 7.4 LTS + Twig）。スクレイパー（Python）は変えない
**Primary Dependencies**: Doctrine ORM・Doctrine Migrations（既存）。新しい依存は無し
**Storage**: MySQL 8.0。`ports` に `slug`・`display_name` を足す（data-model.md）
**Testing**: PHPUnit（`make test-php`）。WebTestCase で `/ports/{slug}`・301・303・sitemap・タイトルを確かめる
**Target Platform**: さくら VPS（`compose.prod.yml`）
**Project Type**: Web（Controller + Twig）
**Performance Goals**: 港のページは `/ports` と同じ処理（ボードを作って絞る）なので、今と同じ
**Constraints**: Cookie `port_filter` の形式を変えない（今の利用者の保存を消さない）。「運行」を書かない
**Scale/Scope**: 港 7・ページ 7 枚の追加。変更するファイルは 15 前後

## Constitution Check

| 原則 | 判定 | 理由 |
|---|---|---|
| I. スクレイパー優先設計 | ✅ | スクレイパーは変えない。`ports` に足す列はスクレイパーが読み書きしない（research R1） |
| II. Webサイト優先（MVP） | ✅ | Controller + Twig のページを足すだけ。API は作らない |
| III. データ品質保証 | ✅ | 運航状況のテーブルには触らない |
| IV. Docker完結 | ✅ | マイグレーションは `make migrate` で入る |
| V. フェーズごとのコミット | ✅ | tasks.md でユーザーストーリーごとに区切り、区切りごとにコミットする |
| 技術スタック・コーディング規約 | ✅ | PSR-12（`make cs-php`）・PHPStan level 7 |

Phase 1 の設計のあとも違反は無い。

## Project Structure

### Documentation (this feature)

```text
specs/18-port-seo-pages/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── http-routes.md
│   └── seo-meta.md
└── tasks.md             # /speckit.tasks で作る
```

### Source Code (repository root)

```text
app/
├── migrations/
│   └── Version20261104000000.php       # ports に slug・display_name（新規）
├── config/packages/twig.yaml           # site_top_title・title_suffix
├── src/
│   ├── Entity/Port.php                 # slug・displayName・getDisplayName()
│   ├── Controller/StatusController.php # port()（新規）・ports() の 301
│   ├── Controller/SeoController.php    # sitemap に港のページ
│   ├── Service/PortFilterResolver.php  # resolveForPort()・古い URL の転送先・url() を slug に
│   └── View/PortFilterResolution.php   # （必要なら）GET の転送を表す
├── templates/
│   ├── base.html.twig                  # 既定の説明文・ナビの「港別」の判定
│   └── status/
│       ├── index.html.twig             # 説明文・「4日分を見る」のリンク
│       ├── ports.html.twig             # 港のページと共用（タイトル・h1・説明文・港へのリンク）
│       ├── _port_links.html.twig       # 港へのリンク（新規）
│       └── company.html.twig           # タイトル・説明文
└── tests/
    ├── Controller/StatusControllerTest.php
    ├── Controller/SeoControllerTest.php
    ├── Controller/ErrorPageTest.php    # suffix の変更
    └── Service/PortFilterResolverTest.php

specs/7-v1-branding/spec.md             # FR-004 を 18 で置き換えたと書く（FR-021）
CLAUDE.md                               # 「サイト名・タイトル…は V1 を引き継ぎ」の行を直す
```

**Structure Decision**: 今の `app/` の構成のまま。港のページは `ports.html.twig` を共用する（`currentPort` があれば港のページ）。同じ内容のテンプレートを 2 つ持たないため。

## 進め方（tasks.md の区切りの目安）

1. **基盤**: マイグレーション・Port エンティティ（slug・displayName）
2. **US1（港のページ）**: `GET /ports/{slug}`・`resolveForPort()`・テンプレートのタイトル・h1・説明文・canonical・港へのリンク・ナビの判定・sitemap
3. **US2（タイトル・説明文）**: twig.yaml の globals・各テンプレートの説明文・既存テストのタイトルの期待値・7-v1-branding と CLAUDE.md の追記
4. **US3（今の使い方を保つ）**: 古い URL の 301・フォームの移り先・トップの「4日分を見る」
5. **仕上げ**: quickstart の手順で確かめる・`make test-php phpstan cs-php lint-php verify-prod`

守る順番は US1 → US3 だけ（US3 は US1 の slug・ルートを使い、どちらも `PortFilterResolver` を触る）。US2 は独立していて、優先度（P1）が US3（P2）より高いので先にする。

## Complexity Tracking

違反は無いので書かない。
