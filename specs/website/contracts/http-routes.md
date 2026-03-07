# HTTP Route Contracts: 運航情報Webサイト

**Phase**: 1 (Contracts)
**Feature**: website
**Date**: 2026-03-07

---

## ルート一覧

### GET `/`

**Controller**: `App\Controller\StatusController::index()`
**Template**: `templates/status/index.html.twig`
**Symfony Route Name**: `app_status_index`

#### 正常系

- **Status**: 200 OK
- **データソース**: `OperationStatusRepository::findTodayByAllCompanies()`
- **Template変数**:
  - `companies`: `array<int, array{company: FerryCompany, routes: array<int, array{route: Route, status: OperationStatus|null}>}>`
  - `today`: `\DateTimeImmutable` （タイトル表示用）

#### リンク要件（FR-003）

- 各フェリー会社名 → `/company/{id}` へのリンク（会社別ページ）
- 各フェリー会社の公式サイト → `FerryCompany::getWebsiteUrl()` を別タブで開く（`target="_blank"`）

#### データなしの場合

- **Status**: 200 OK（500にしない - SC-004）
- **挙動**: `companies` が空配列 or 各Routeの OperationStatus が null → 「現在情報がありません」メッセージを表示

---

### GET `/company/{id}`

**Controller**: `App\Controller\StatusController::company(int $id)`
**Template**: `templates/status/company.html.twig`
**Symfony Route Name**: `app_status_company`

#### 正常系

- **Status**: 200 OK
- **データソース**:
  - `FerryCompanyRepository::find($id)` → FerryCompany
  - `OperationStatusRepository::findRecentByCompany($company, 3)` → 直近3日分
- **Template変数**:
  - `company`: `FerryCompany`
  - `statuses`: `array<string, array<int, array{route: Route, status: OperationStatus|null}>>` （キー: `'Y-m-d'` 形式の日付文字列）

#### リンク要件（FR-003）

- ページ上部に「< トップへ戻る」→ `app_status_index` へのリンク
- 会社名横に公式サイトへのリンク → `FerryCompany::getWebsiteUrl()` を別タブで開く（`websiteUrl` が null の場合は非表示）

#### 存在しないID

- **Status**: 404 Not Found
- **実装**: `$this->createNotFoundException()` を throw

---

## Symfony Routingアノテーション（参考）

```php
#[Route('/', name: 'app_status_index')]
public function index(): Response {}

#[Route('/company/{id}', name: 'app_status_company')]
public function company(int $id): Response {}
```

---

## 対象外（P3・MVP以降）

| URL | 理由 |
|---|---|
| `GET /route/{id}` | P3。`show_route_detail`カラム追加含め次フェーズ。 |
| REST API endpoints | Constitution II. REST APIはMVP以降。 |
