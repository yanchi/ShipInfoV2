# Research: 運航情報Webサイト

**Phase**: 0 (Outline & Research)
**Feature**: website
**Date**: 2026-03-07

---

## Decision Log

### 1. CSSフレームワーク選定

- **Decision**: Bootstrap 5 をCDN経由で導入
- **Rationale**: spec.mdに明記済み。Webpack Encore等のビルドチェーンを追加せずMVPを最速で動かせる。PHPUnitテストに影響しない。
- **Alternatives considered**:
  - Webpack Encore + Bootstrap NPM: ビルド環境追加でMVP遅延。却下。
  - Tailwind CSS CDN: コンポーネントが少なくBootstrapより手間。却下。
  - 素のCSS: モバイル対応(FR-006)の工数増大。却下。

### 2. DBアクセス方法（N+1 vs JOIN）

- **Decision**: `OperationStatusRepository` に2本のメソッドを追加してN+1を回避。DQL と raw SQL のハイブリッド実装を採用。
- **Rationale**: トップページで全社×全航路×本日のステータスを効率よく取得する。会社2社・航路5〜10本のMVP規模でも、N+1は設計負債になる。`MAX(scraped_at)` サブクエリを含む複雑な集計クエリはDQLで表現が難しいため、ステータス取得部分には raw SQL (`$conn->executeQuery()`) を使用し、Entity変換は `findBy(['id' => $ids])` でバッチ取得する。
- **実装詳細**:
  - FerryCompany・Route の取得: DQL（Doctrine Entityとして取得）
  - OperationStatus の最新1件取得: raw SQL（`INNER JOIN` + `MAX(scraped_at)` サブクエリ）
  - Entity変換: `findBy(['id' => $ids])` でバッチ取得（Doctrine Identity Map でN+1回避）
- **Alternatives considered**:
  - Doctrine遅延ローディング（デフォルト）: N+1クエリ発生。ページ表示ごとに10〜20クエリ。却下。
  - 純粋DQL: `MAX(scraped_at)` サブクエリがDQLで記述困難。却下。

### 3. P3（航路別詳細ページ）のスコープ

- **Decision**: P3はMVPスコープ外。`show_route_detail`カラムも今回追加しない。
- **Rationale**: spec.mdで「Priority: P3」「MVP後に検討」と明記。P1・P2のみ実装してMVP価値を最速提供。
- **Alternatives considered**:
  - P3も一緒に実装: スコープ拡大、コミット原則違反リスク。却下。
  - DBカラムだけ先に追加: 使わないカラムを追加するのはYAGNI。却下。

### 4. テンプレート構成

- **Decision**: `templates/base.html.twig` を拡張、`templates/status/` 配下に機能別テンプレートを配置
- **Rationale**: Symfonyの標準的なTemplate Inheritance。既存の`base.html.twig`が既にある。
- **Alternatives considered**:
  - 独立したHTMLファイル: Twigのblock継承を活用できない。却下。

### 5. Controller設計

- **Decision**: `App\Controller\StatusController` に `index()` と `company()` の2アクションを実装
- **Rationale**: spec.mdで `StatusController` が明示されている。1コントローラーに2アクションはSymfony標準パターン。
- **Alternatives considered**:
  - 会社別に別Controller: 会社数が少ないMVPでは過剰設計。却下。

### 6. 404ハンドリング

- **Decision**: `company()` アクションで `FerryCompanyRepository::find()` がnullの場合、`$this->createNotFoundException()` を使用
- **Rationale**: Symfonyの標準404ハンドリング。FR-005準拠。
- **Alternatives considered**:
  - カスタム例外クラス: MVP段階では不要。却下。

### 7. ステータス表示ロジックの置き場

- **Decision**: Twigテンプレート内でステータス値に応じてCSSクラスとラベルを切り替える（`OperationStatusEnum`のvalueをmatch的に使う）
- **Rationale**: 表示ロジックはViewに閉じるのがMVPとして最もシンプル。将来Twig Extensionに移せる。
- **Alternatives considered**:
  - Twig Extension/Filter: 抽象化が早すぎる。YAGNI。却下。
  - Controller側でDTO変換: ViewModel層の追加は過剰設計。却下。

---

## 技術コンテキスト（確定済み）

| 項目 | 値 |
|------|-----|
| PHP | 8.3 |
| Symfony | 7.4 LTS |
| テンプレートエンジン | Twig |
| CSS | Bootstrap 5 (CDN) |
| ORM | Doctrine ORM |
| DB | MySQL 8.0 |
| テスト | PHPUnit |
| 既存Entity | FerryCompany, Route, OperationStatus, ScraperLog |
| 既存Enum | OperationStatusEnum (operating/cancelled/delayed/suspended/unknown) |

NEEDS CLARIFICATIONなし。すべて解決済み。
