# Data Model: 運航に変更がある便をメールで知らせる

**Feature**: [spec.md](spec.md) | **Research**: [research.md](research.md)

既存の `operation_statuses`・`departure_statuses` は読むだけで変えない。新しく持つのは「通知の確認回」だけ。

---

## 1. NotificationRun（新規テーブル `notification_runs`）

通知の確認回（日付 × 時刻枠）を 1 行で表す。二重送信を防ぐ（FR-009）のと、その回がどうなったかを追う（US3）のに使う。

| 列 | 型 | NULL | 内容 |
|---|---|---|---|
| `id` | INT UNSIGNED AUTO_INCREMENT | NO | 主キー |
| `run_date` | DATE | NO | 確認した日（日本時間） |
| `slot` | TINYINT UNSIGNED | NO | 時刻枠（1・6・15） |
| `result` | VARCHAR(32) | NO | `NotificationResultEnum`（下記） |
| `item_count` | INT UNSIGNED | NO | メールに載せた件数（まとめた後）。送っていなければ 0 |
| `error_message` | TEXT | YES | 失敗したときのエラーの要約（DSN・パスワードは含めない） |
| `created_at` | DATETIME | NO | 回を確保した時刻 |
| `updated_at` | DATETIME | NO | 結果を書いた時刻 |

- **一意キー**：`uniq_notification_run (run_date, slot)`
- **保持期間**：90 日。コマンドの最後に `run_date < 今日 - 90日` の行を消す（research R3）
- **書くのは** PHP のコマンドだけ。スクレイパーは触らない（`scraper/scraper/db/models.py` にモデルは足さない）
- 作るのは Doctrine のマイグレーション（`app/migrations/Version2026100600000*.php`）。`01_schema.sql` には足さない（ほかの後から足したテーブルと同じ）

### NotificationResultEnum（`app/src/Enum/NotificationResultEnum.php`）

| 値 | 意味 |
|---|---|
| `pending` | 回を確保した。まだ結果が無い（送信の途中で落ちたらこのまま残る。再送しない） |
| `sent` | 1 件以上あり、送った |
| `none` | 通常運航以外の便が 0 件。送っていない |
| `not_configured` | `MAILER_DSN`・`NOTIFY_FROM`・`NOTIFY_TO` のどれかが無い。送っていない |
| `failed` | 送信で例外。送れていない |

### 状態の遷移

```
（行なし）──INSERT 成功──▶ pending ──┬─▶ sent
     │                               ├─▶ none
     │                               ├─▶ not_configured
     │                               └─▶ failed
     └──INSERT が一意キーに当たる──▶ 何もしない（すでに確保されている回）
```

`pending` 以外から別の値には変えない。同じ回をやり直す仕組みは作らない（FR-009・FR-010）。

---

## 2. 通知の便（表示専用。DB には持たない）

確認時点の `operation_statuses`・`departure_statuses` から組み立てる（Constitution III：新しい履歴は持たない）。

### IrregularService（`app/src/View/IrregularService.php`）

(航路, 日付) ごとに 1 つ。メールの 1 件。

| プロパティ | 型 | 内容 |
|---|---|---|
| `company` | `FerryCompany` | 会社 |
| `route` | `Route` | 航路 |
| `date` | `\DateTimeImmutable` | 運航日（航路×日付は `valid_date`、港だけのときは `departure_date`） |
| `routeStatus` | `?OperationStatus` | 航路×日付の最新行。無ければ null |
| `ports` | `list<IrregularPort>` | 通常運航以外の港（出港予定時刻順。時刻が無いものは最後） |

- `isRouteIrregular()`：`routeStatus` の状態が対象（cancelled・delayed・suspended・unknown）か
- 組み立ての条件：`isRouteIrregular()` か `ports !== []` のどちらか（両方 false のものは作らない）
- `directionLabel()`：`route.direction?.label() ?? route.name`
- `statusText()`：
  - 航路が対象 → `routeStatus.status.label()`
  - 航路が通常運航 → `通常運航（途中の港に変更あり）`
  - 航路の行が無い・no_service → `情報なし（途中の港に変更あり）`
- `detail()`：航路が対象のときの `routeStatus.statusDetail`（空なら null）

### IrregularPort（`app/src/View/IrregularPort.php`）

| プロパティ | 型 | 内容 |
|---|---|---|
| `portName` | `string` | 出発港 |
| `shipName` | `?string` | 船名（空文字は null） |
| `departureAt` | `?\DateTimeInterface` | 出港予定 |
| `status` | `OperationStatusEnum` | cancelled・delayed・suspended・unknown のどれか |
| `detail` | `?string` | 備考 |

### 並び（FR-006）

会社 ID → 日付 → 航路 ID。サイトの会社の並び（`fc.id` 順）と同じ。

### 対象の範囲（research R5）

- 日付：今日〜3 日先（`StatusController::PORT_BOARD_DAYS` を `PortBoardBuilder::DAYS` に移して共有する）
- 有効な会社・有効な航路。港ごとは direction のある航路だけ（`findForBoard` と同じ）
- 状態：cancelled・delayed・suspended・unknown

---

## 3. 既存への小さな変更

### OperationStatusEnum に `label()` を足す

| 値 | label |
|---|---|
| operating | 通常運航 |
| delayed | 条件付・遅延 |
| cancelled | 欠航 |
| suspended | 運休 |
| unknown | 不明 |
| no_service | 便なし |

`isIrregular(): bool` も足す（delayed・cancelled・suspended・unknown で true）。通知の判定はこれ1か所で行う。

ステータスバッジ（`_status_badge.html.twig`）は記号 + `status.label()` にし、サイトとメールの文言を一致させる（見た目・文言は今と同じ）。

### Repository に足すクエリ

| メソッド | 内容 |
|---|---|
| `OperationStatusRepository::findLatestBetween(\DateTimeImmutable $from, int $days): list<OperationStatus>` | 有効な会社・有効な航路の、航路×日付ごとの最新行（全状態）。航路・会社を JOIN して取る。港だけ通常以外の便にも `routeStatus` を付けるため状態では絞らず、対象かどうかは PHP で `isIrregular()` を見る（4 日 × 航路数で数十行） |
| `DepartureStatusRepository::findIrregularBetween(\DateTimeImmutable $from, int $days): list<DepartureStatus>` | `findForBoard` と同じ範囲・JOIN で、状態が対象（`isIrregular()` の値）のもの |
