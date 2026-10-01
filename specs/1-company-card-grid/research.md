# Phase 0: Research — トップページ会社カード横並びグリッド

**Feature**: `1-company-card-grid` | **Date**: 2026-03-08

---

## R-001: グリッド実装方式（Bootstrap ユーティリティ vs カスタムCSS）

**Decision**: Bootstrap 5 の `row-cols-*` ユーティリティクラスを使用する。カスタムCSSは書かない。

**Rationale**:
- [base.html.twig](../../app/templates/base.html.twig) は既に Bootstrap 5.3.3 を CDN で読み込んでおり、`row-cols-1 row-cols-md-2 row-cols-lg-3` の1行追加でFR-001〜FR-004を満たせる。
- 現在 `app/public/` には `index.php` しか存在せず、CSSアセットは1つもない。カスタムCSSを入れると「アセットパイプラインなしで生CSSを配信する」という新しい前例を作ることになり、Constitution の「技術的負債は即日解消」に反する。
- ブレークポイントの折り返し・ガター・レスポンシブ挙動はすべて Bootstrap 側でテスト済み。自前実装するとブラウザ差異の検証コストが乗る。

**Alternatives considered**:
- **カスタム CSS Grid（`app/public/css/app.css` 新規作成）**: spec 当初案の 600px/900px ブレークポイントを正確に再現できるが、CSSファイル + `base.html.twig` への `<link>` 追加が必要。ブレークポイントの精度は本機能の価値（会社間の視覚的公平性）に寄与しないため不採用。
- **Flexbox wrap（`d-flex flex-wrap` + 幅ユーティリティ）**: `row-cols-*` と同等の結果になるが記述が冗長。不採用。

---

## R-002: ブレークポイント値の確定

**Decision**: Bootstrap 5 標準の `md` = 768px / `lg` = 992px を採用し、spec の FR-002〜FR-004 をこの値に更新する。

**Rationale**:
- spec 当初案は 600px / 900px だったが、これは Bootstrap の `md`/`lg` を近似した値として設定されたもの（[checklists/requirements.md](checklists/requirements.md) に「実装時に調整可能」と明記済み）。
- 実際の Bootstrap 標準値は 768px / 992px。標準値を採用すればカスタムCSSが不要になる（R-001 の前提）。
- 折り返し幅が 100〜200px ずれても SC-001（縦スクロール量削減）・SC-002（表示位置による優劣なし）・SC-003（375px で可読）はすべて達成される。

**確定するレイアウト**:

| 画面幅 | 列数 | Bootstrap クラス |
|---|---|---|
| < 768px | 1列 | `row-cols-1` |
| 768〜991px | 2列 | `row-cols-md-2` |
| ≥ 992px | 3列 | `row-cols-lg-3` |

**Alternatives considered**:
- **`row-cols-sm-2`（576px）を使う**: 599px 時に2列になり、モバイル要件（1列）を外す。また 900〜991px が2列のままで「デスクトップ3列」の体感とズレる。不採用。
- **カスタムCSSで 600/900 を厳守**: R-001 で不採用。

---

## R-003: カード高さの揃え方

**Decision**: 各カードに `h-100` を付与し、同一行内で高さを揃える。

**Rationale**:
- 会社ごとに航路数が異なる（マリックスラインは下り・上りの2航路、マルエーフェリーも2航路だが将来的に増減しうる）ため、自然高さのままだとカード下端がガタつく。
- `row-cols-*` の各 `.col` は Grid セルとして同じ高さを持つので、内側の `.card` に `h-100` を付ければセル高いっぱいに伸びる。追加CSS不要。
- 本機能の目的は「会社間の視覚的な優劣をなくす」こと。高さがバラつくと大きいカードが目立ち、目的に反する。

**Alternatives considered**:
- **自然な高さ（spec 当初案）**: 実装は `h-100` を付けないだけで簡単だが、上記の理由で目的に反する。spec の Edge Cases を更新して不採用とした。

---

## R-004: DOM構造の変更範囲

**Decision**: `{% for %}` ループの外側に `<div class="row ...">` を1つ追加し、ループ内の `<div class="card mb-4">` を `<div class="col"><div class="card h-100">` に置き換える。カード内部（`card-header` 以下）は一切変更しない。

**Rationale**:
- FR-005（カード内部コンテンツ不変）を構造的に保証する。差分がラッパー部分だけに閉じるため、レビュー時にデグレードの有無が一目で分かる。
- `mb-4`（下マージン）は不要になる。行間は `row` の `g-4`（ガター）が担当するため、`mb-4` を残すと行間が二重に空く。

**Alternatives considered**:
- **カード内部も同時にリファクタ**: FR-005 に違反するリスクがあり、本機能のスコープ外。不採用。

---

## R-005: テスト方針

**Decision**: 既存の [StatusControllerTest.php](../../app/tests/Controller/StatusControllerTest.php) に、グリッド構造の存在を検証する機能テストを追加する。ブラウザでの見た目確認は quickstart.md の手動手順でカバーする。

**Rationale**:
- PHPUnit の `WebTestCase` は DOM セレクタ検証（`assertSelectorExists`）ができるので、`.row.row-cols-1.row-cols-md-2.row-cols-lg-3` の存在と `.col > .card.h-100` の構造はテスト可能。
- 一方、実際の折り返し列数は CSS の適用結果でありサーバーサイドテストでは検証不能。ブラウザのデバイスエミュレーター（375px / 800px / 1200px）での目視確認を quickstart に記載する。
- E2E テスト基盤（Playwright 等）は現プロジェクトに存在せず、CSSクラス1行の変更のために導入するのは過剰。Constitution の MVP 方針に反する。

**Alternatives considered**:
- **Playwright / Panther を導入してビジュアルリグレッションテスト**: 導入コストが変更規模に見合わない。不採用。
- **テストを追加しない**: FR-001 の充足がコードレビュー頼りになる。デグレード検知のため最低限の構造テストは入れる。

---

## 未解決事項

なし。すべての NEEDS CLARIFICATION は解決済み。
