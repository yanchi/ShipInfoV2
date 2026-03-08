# Research: no_service ステータス追加

**Date**: 2026-03-08
**Branch**: `3-no-service-status`

---

## 1. 既存コードベース調査結果

### Python OperationStatusEnum（`scraper/scraper/db/models.py`）

現在の値:
```python
class OperationStatusEnum(str, enum.Enum):
    operating = "operating"
    cancelled = "cancelled"
    delayed   = "delayed"
    suspended = "suspended"
    unknown   = "unknown"
```

→ `no_service = "no_service"` を追加するだけ。

### PHP OperationStatusEnum（`app/src/Enum/OperationStatusEnum.php`）

現在:
```php
enum OperationStatusEnum: string {
    case Operating = 'operating';
    case Cancelled = 'cancelled';
    case Delayed   = 'delayed';
    case Suspended = 'suspended';
    case Unknown   = 'unknown';
}
```

→ `case NoService = 'no_service';` を追加するだけ。

### DB スキーマ

`operation_statuses.status` カラムは現在 **VARCHAR(255)**（Doctrine Migration で ENUM → VARCHAR に変更済み）。
MySQL ENUM 変更は不要。`no_service` の文字列を保存するだけで OK。

→ **DBマイグレーション不要**。

### PHP Entity（`app/src/Entity/OperationStatus.php`）

```php
#[ORM\Column(type: 'string', enumType: OperationStatusEnum::class)]
private OperationStatusEnum $status = OperationStatusEnum::Unknown;
```

カラム型は `string`、PHP Enum で値を管理している。PHP Enum に `NoService` を追加するだけで Doctrine も正しく扱える。Doctrine の `migrate-diff` を実行しても schema 変更は発生しない（文字列カラムのまま）。

---

## 2. 便無し判定の設計

### マルエーフェリー（既実装）

`fetch()` が POST 検索を行い、結果が空なら `self._has_service = False` + `""` を返す。
`parse()` の no-service パスで現在 `OperationStatusEnum.cancelled` を記録している。
→ これを `OperationStatusEnum.no_service` に変えるだけ。

### マリックスライン（新規設計）

**Decision**: parse 後に「今日の記録がないルート」を検出して `no_service` を記録する。

**Rationale**:
- `https://marixline.com/service/` は常にページを返す（fetch() は常に HTML を返す）
- 各ブロックは `div.info2` の日付 (`YYYY年M月D日`) が `valid_date`
- 当日の便がなければ当日日付のブロックが存在しない
- parse 後に `seen = set[tuple[route_id, date]]` を参照し、`(route.id, date.today())` が未登録のルートに `no_service` を追加

**Alternatives considered**:
- fetch() に「サービス有無チェック」ステップを追加 → マルエーフェリー方式だが、マリックスラインのサイトには専用検索エンドポイントがない。不採用。
- seen に `route.id` だけで確認（「任意の日付でもよい」） → 他日の記録があっても今日が便なしの場合を見逃す。不採用。

### 既存テストへの影響

既存の MarixLine テストは HTML 内の日付として `2026-03-07`（過去）を使っており、`date.today()` は `2026-03-08`。
変更後: parse 後のループで「今日 (2026-03-08) のレコードがない」と判定され、no_service レコードが追加されるため、`len(records)` のアサーションが変わる。

→ **既存テストを `unittest.mock.patch` で `date.today()` を HTML 内の日付に合わせてモックする形に修正する**。

---

## 3. 変更対象ファイル一覧

| ファイル | 変更内容 |
|---|---|
| `scraper/scraper/db/models.py` | `OperationStatusEnum` に `no_service` 追加 |
| `app/src/Enum/OperationStatusEnum.php` | `NoService` ケース追加 |
| `scraper/scraper/scrapers/marue_ferry.py` | no-service パスで `cancelled` → `no_service` |
| `scraper/scraper/scrapers/marix_line.py` | parse 後に no_service 追加ロジック |
| `scraper/tests/test_marue_ferry.py` | no-service テストのアサーション更新 |
| `scraper/tests/test_marix_line.py` | 既存テストのモック修正 + no_service テスト追加 |

---

## 4. リスクと対策

| リスク | 対策 |
|---|---|
| MarixLine ページが別日（翌日など）のブロックしか持たない場合 | 今日のブロックがなければ no_service を記録する仕様なので意図通り |
| parse 結果が空（ページ取得失敗）でも no_service が記録される | マリックスラインは現状 fetch() で raise_for_status() しているため空 HTML は来ない |
| PHP 側で `no_service` 値を読み込めない | `OperationStatusEnum::NoService` 追加で対応 |
| 既存の `unknown` との混同 | `no_service` は「便なし」、`unknown` は「判定不能」として明確に区別されている |
