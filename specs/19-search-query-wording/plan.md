# Implementation Plan: 検索語に合わせた会社ページの説明文と船の名前

**Branch**: `19-search-query-wording` | **Date**: 2026-11-24 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/19-search-query-wording/spec.md`

## Summary

会社ページのタイトルに「リアルタイム」を入れ、説明文を「公式より早く・まとめて分かる」内容にする。説明文にだけ「運航（運行）状況」を 1 回添える（トップ・港別・港のページも同じ）。
`ferry_companies` に船の名前・別名（JSON、NULL 可）を足してマイグレーションで 2 社分を入れ、会社ページの h1 のすぐ下に小さい1行で出し、船の名前は説明文の最後にも入れる。

## Technical Context

**Language/Version**: PHP 8.3（Symfony 7.4 LTS + Twig）。スクレイパー（Python）は変えない
**Primary Dependencies**: Doctrine ORM・Doctrine Migrations（既存）。新しい依存は無し
**Storage**: MySQL 8.0。`ferry_companies` に `ship_names`・`aliases`（JSON、NULL 可）を足す（data-model.md）
**Testing**: PHPUnit（`make test-php`）。WebTestCase でタイトル・説明文・1行・「運行」の出る場所を確かめる
**Target Platform**: さくら VPS（`compose.prod.yml`）
**Project Type**: Web（Controller + Twig）
**Performance Goals**: 会社ページは同じ行を読むだけなので、今と同じ
**Constraints**: 「運行」は meta description・og:description にだけ。スクレイパーのモデル・テストを変えずに済むよう列は NULL 可（research R2）
**Scale/Scope**: 列 2 つ・テンプレート 3 枚・テスト 1 ファイル。変更するファイルは 10 前後

## Constitution Check

| 原則 | 判定 | 理由 |
|---|---|---|
| I. スクレイパー優先設計 | ✅ | スクレイパーは変えない。足す列は NULL 可で、スクレイパーは読み書きしない（research R2） |
| II. Webサイト優先（MVP） | ✅ | Twig の文言と1行を変えるだけ。API は作らない |
| III. データ品質保証 | ✅ | 運航状況のテーブルには触らない |
| IV. Docker完結 | ✅ | マイグレーションは `make migrate` で入る |
| V. フェーズごとのコミット | ✅ | tasks.md でユーザーストーリーごとに区切り、区切りごとにコミットする |
| 技術スタック・コーディング規約 | ✅ | PSR-12（`make cs-php`）・PHPStan level 7 |

Phase 1 の設計のあとも違反は無い。

## Project Structure

### Documentation (this feature)

```text
specs/19-search-query-wording/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── seo-meta.md
└── tasks.md             # /speckit.tasks で作る
```

### Source Code (repository root)

```text
app/
├── migrations/
│   └── Version20261124000000.php       # ferry_companies に ship_names・aliases と 2 社の値（新規）
├── src/
│   └── Entity/FerryCompany.php         # shipNames・aliases と getter・setter
├── templates/
│   └── status/
│       ├── company.html.twig           # タイトル・説明文・船の名前の1行
│       ├── index.html.twig             # 説明文に「運航（運行）」
│       └── ports.html.twig             # 説明文に「運航（運行）」（全港・港の両方）
└── tests/
    └── Controller/StatusControllerTest.php  # 「運行」の出る場所・タイトル・説明文・1行

specs/18-port-seo-pages/spec.md         # Clarifications に「19 で description だけ変えた」
CLAUDE.md                               # 「タイトル・説明文は 18-port-seo-pages で…」の行に 19 を足す
```

**Structure Decision**: 今の `app/` の構成のまま。会社ページに渡している `company`（FerryCompany）から船の名前・別名を読むので、Controller は変えない。

## 進め方（tasks.md の区切りの目安）

1. **基盤**: マイグレーション・FerryCompany（shipNames・aliases）
2. **US1（会社ページのタイトル・説明文と「運行」）**: company.html.twig のタイトル・説明文、index・ports の説明文、既存テストの期待値と「運行」のテストの書き換え（research R6）
3. **US2（船の名前・別名）**: company.html.twig の1行と説明文の「運航船：」、テスト（あり・なし・片方だけ）
4. **仕上げ**: 18 の spec・CLAUDE.md の追記、quickstart の手順で確かめる、`make test-php phpstan cs-php lint-php verify-prod`

US1 は基盤が無くても進められる（説明文の「運航船：」は US2 で足す）。US2 は基盤のあと。

## Complexity Tracking

違反は無いので書かない。
