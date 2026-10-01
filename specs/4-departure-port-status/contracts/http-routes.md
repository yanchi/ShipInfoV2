# HTTP Route Contracts: 出発港別の運航情報表示

**Phase**: 1 (Contracts)
**Feature**: 4-departure-port-status
**Date**: 2026-10-01

既存の `/` と `/company/{id}` は、ルート・テンプレート変数とも変更しない（[specs/website/contracts/http-routes.md](../../website/contracts/http-routes.md)）。

---

## 新規: GET `/ports`

**Controller**: `App\Controller\StatusController::ports()`
**Template**: `templates/status/ports.html.twig`
**Symfony Route Name**: `app_status_ports`

### 正常系

- **Status**: 200 OK
- **データソース**: `DepartureStatusRepository::findForBoard(\DateTimeImmutable $from, int $days)` → `PortBoardBuilder::build()`
- **表示範囲**: 今日（JST）から3日先までの4日分（FR-010）。過去の日付は出さない
- **Template変数**:
  - `board`: `App\View\PortBoard`（[data-model.md](../data-model.md) の「表示用」）
  - `today`: `\DateTimeImmutable`

### 画面の構成（暫定。見せ方は別の要件で見直す）

```
港別運航情報
10月1日（木）
  下り（那覇行き）
    鹿児島発 → 那覇   [通常運航]  フェリー波之上／マルエーフェリー  18:00発（翌19:00着）  17:30時点
    名瀬発   → 那覇   [欠航]      クイーンコーラルプラス／マリックスライン  05:50発 …  17:30時点
                       └ 台風接近のため欠航
    …
  上り（鹿児島行き）
    那覇発   → 鹿児島 …
10月2日（金）
  …
10月4日（日）
  下り（那覇行き）
    名瀬発   → 那覇   [運航予定]  フェリーあけぼの／マルエーフェリー  05:50発
```

### 各行（エントリ）に出す項目

| 項目 | 出所 | 必須 |
|---|---|---|
| 出発港 → 到着港 | `ports.name`、方向の終点 | ✅ |
| ステータスバッジ | `DepartureDisplayState`（下表） | ✅ |
| 会社名・船名 | `ferry_companies.name`、`ship_name` | 便がある行 |
| 出港予定時刻・到着予定時刻 | `scheduled_departure_at` / `scheduled_arrival_at`（FR-017）。日付が違えば「翌19:00着」のように出す | 取れた場合 |
| 詳細テキスト | `status_detail`（FR-008） | ある場合 |
| 最終確認時刻 | `checked_at` →「n/j H:i時点」（FR-014） | 行がある場合 |

### バッジ

既存のバッジ（通常運航・条件付・遅延・欠航・運休・便なし・不明・情報なし）は、ラベルと色を変えない（FR-011）。共通のパーシャル `templates/status/_status_badge.html.twig` にまとめて、3つのテンプレートで使い回す。

| 状態 | ラベル | 見た目 |
|---|---|---|
| `scheduled` | 運航予定 | 新規。緑系は使わない中立の見た目（例：`bg-light text-dark border` に枠線の点線）。通常運航と見分けがつくこと |
| `no_info` | 情報なし | 既存の「情報なし」と同じ |
| `no_service` | 便なし | 既存の「便なし」と同じ |

### データなしの場合

- **Status**: 200 OK（500にしない）
- 港マスタや route_stops が空 → 「港別の情報がありません。」
- 行のデータが無い → 各行を `no_info` で出す（行は消さない。SC-003）

### 導線

- トップページ（`/`）の見出しの下に「港別に見る →」リンク（`app_status_ports`）を1つ足す。トップのカードの構成は変えない（FR-010）
- `/ports` の上部に「← トップへ戻る」
