# Implementation Plan: OG 画像を出す

**Branch**: `10-og-image` | **Date**: 2026-10-06 | **Spec**: [spec.md](spec.md)

---

## Summary

全ページ共通の OG 画像（1200×630 の PNG）を `app/public/og-image.png` に置き、`base.html.twig` の `<head>` に og:image（リクエストのホストの絶対 URL）・type・width・height・alt を足し、twitter:card を summary_large_image にする。画像は HTML で書いた元をヘッドレス Chrome で PNG にしてリポジトリに入れる。DB・スクレイパー・ルートは変えない。

---

## Technical Context

**Language/Version**: PHP 8.3
**Primary Dependencies**: Symfony 7.4、Twig。新しい依存は無い
**Storage**: 変更なし
**Testing**: PHPUnit（Controller の機能テスト、画像ファイルの寸法・大きさ）
**Target Platform**: Docker Compose（開発）、さくら VPS の `compose.prod.yml`（本番）
**Project Type**: Web アプリ（MVP、Twig）
**Performance Goals**: ページの DB クエリ・リクエストは増やさない（画像は SNS のクローラーが取りに来るだけで、ページの表示では読まない）
**Constraints**:
- 画像は 300KB 以下（FR-004）
- og:image はリクエストのホストを指す（ローカルで本番を指さない）
- 「ShipInfo」を画像にもタグにも出さない
**Scale/Scope**: 画像 1 枚、テンプレート 1 つ、globals 1 つ、テスト 2 ファイル

未解決の NEEDS CLARIFICATION は無い（[research.md](research.md)）。

---

## Constitution Check

| Gate | Status | 備考 |
|---|---|---|
| I. スクレイパー優先設計 | ✅ PASS | スクレイパーは変更しない |
| II. Twig + Controller、API なし | ✅ PASS | テンプレートと静的ファイルだけ |
| III. データ品質・キーごとの最新状態 | ✅ PASS | DB を変えない |
| IV. Docker で完結 | ✅ PASS | PNG をリポジトリに入れるので、起動・テスト・ビルドにホストの道具は要らない。Chrome を使うのは画像を作り直すときだけ（research R2） |
| V. フェーズごとにコミット・スコープを制限 | ✅ PASS | 1 PR。tasks.md のグループごとにコミット |
| 技術スタック（変更禁止） | ✅ PASS | 依存の追加なし |

**Phase 1 設計の後に再チェック**: 違反は無し。

---

## Project Structure

### Documentation

```
specs/10-og-image/
├── spec.md
├── research.md
├── data-model.md
├── contracts/
│   └── head-meta.md
├── quickstart.md
├── og-image.html    # 画像の元（implement で作る）
├── plan.md          ← このファイル
└── tasks.md         （/speckit.tasks で生成）
```

### 変更対象

```
app/public/og-image.png                    # 新規：OG 画像（1200×630 PNG）
app/config/packages/twig.yaml              # globals に og_image_alt
app/templates/base.html.twig               # og:image・type・width・height・alt、twitter:card = summary_large_image

app/tests/Controller/StatusControllerTest.php   # testHeadMetaOnAllPages を書き換え、画像ファイルのテストを足す
app/tests/Controller/ErrorPageTest.php          # 404 のページの og:image

specs/7-v1-branding/spec.md                # FR-008 を 10-og-image で置き換えた旨（specify で済み）
CLAUDE.md                                  # 「重要な設計決定」の OG の行に OG 画像を 1 行
```

**Structure Decision**: 既存の `<head>` の組み立て（7-v1-branding R6）に足すだけ。画像は `favicon.svg` と同じく `public/` 直下の静的ファイル（research R3）。

---

## 主な設計判断（詳細は research.md）

| 判断 | 内容 | research |
|---|---|---|
| 形式 | PNG | R1 |
| 作り方 | HTML の元 → ヘッドレス Chrome で PNG、リポジトリに入れる | R2 |
| 置き場所 | `public/og-image.png` | R3 |
| URL | `app.request.schemeAndHttpHost ~ '/og-image.png'` | R4 |
| タグ | og:image・type・width・height・alt、twitter:card = summary_large_image | R5 |
| 文言 | alt は globals の `og_image_alt` | R6 |
| 見た目 | V1 の青地、ファビコンの船、白い太字のサイト名 | R7 |
| テスト | head のタグ＋画像の寸法・大きさ | R8 |

## Complexity Tracking

違反は無いので記載なし。
