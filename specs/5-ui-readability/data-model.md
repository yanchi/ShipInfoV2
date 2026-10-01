# Data Model: 運航情報画面の見やすさ改善

**Feature**: [spec.md](spec.md) | **Date**: 2026-10-01

**DB の変更は無い。** テーブル・カラム・マイグレーションは追加しない。
追加・変更するのは表示用オブジェクト（`app/src/View/`）と、読み取り専用のリポジトリメソッドだけ。

---

## 表示用オブジェクト（`app/src/View/`）

### PortFilter（新規）

港別ページの絞り込み条件。

| フィールド | 型 | 説明 |
|---|---|---|
| `portId` | `?int` | 出発港の ID。`null` は全港 |
| `direction` | `?RouteDirectionEnum` | 方向。`null` は両方向 |

- `isActive(): bool` … どちらかが指定されていれば true
- `matches(RouteDirectionEnum $direction, Port $port): bool`
- `toQuery(): array` … `['port' => .., 'dir' => ..]`（URL・Cookie 用）
- `label(list<Port> $ports): ?string` … 「和泊発・下り」のような絞り込み中の表示
- `static none(): self`

**作り方**（`PortFilterResolver`、Service）:
1. クエリに `port` か `dir` がある → それで表示する。`port=all` は全港。Cookie は読む（`hasSaved` のため）が、表示には使わず書き換えない
2. 無ければ Cookie `port_filter` の値を使う
3. どちらも無い → `none()`

**保存**（`PortFilterResolver::submit()` が Controller に返す指示。`POST /ports/filter`、PR #33 レビュー）:
- `action=save` → 値が正しく CSRF トークンも正しければ Cookie を書き、条件の GET の URL にリダイレクトする。どちらかが不正なら書かない（もとの Cookie は残す）
- `action=clear` → CSRF トークンが正しければ Cookie を消し、`/ports` にリダイレクトする
- `action=show` → Cookie は変えず、条件の GET の URL にリダイレクトする
- GET の `save`・`clear` は受け付けない

**検証**: 港 ID が港別ページの出発港（`findBoardStops()` に出る港）に無い、または `dir` が `down` / `up` 以外なら、その値は `null` 扱いにする。Cookie 由来で不正なら Cookie を消す。

- `hasSaved: bool` … Cookie に保存した条件があるか（「保存を解除」を出すかの判定）

**トップ用**: `resolveFromCookie()` はクエリを見ず Cookie だけを読む（`save`・`clear` も受け付けないので、リダイレクトしない）。Cookie が不正なら港別ページと同じく消す

### PortBoard（変更）

| 追加メソッド | 説明 |
|---|---|
| `filter(PortFilter $filter): PortBoard` | 絞り込み条件に合う方向・行だけを残した新しいボードを返す。日付は全部残す |
| `forCompany(int $companyId): PortBoard` | その会社の便（`state` が `status` / `scheduled`、`companyId` が一致）のエントリーだけを残す。エントリーが無くなった行・方向は落とす |
| `lastCheckedAt(): ?DateTimeInterface` | ボード内の最大の確認時刻 |

### PortBoardDirection（変更）

| 追加メソッド | 説明 |
|---|---|
| `commonCheckedAt(): ?DateTimeInterface` | 確認時刻を持つエントリーが全部同じ分（`Y-m-d H:i`）ならその時刻。違えば `null` |

### PortBoardEntry（変更）

| 追加フィールド | 型 | 説明 |
|---|---|---|
| `companyId` | `?int` | 便の会社の ID（他社運航のエントリーは運航会社の ID）。ルール5（行が無い）の「情報なし」は `null`。`PortBoardBuilder` はエントリーを作るときに入れるだけで、判定ルールは変えない |

| 追加メソッド | 説明 |
|---|---|
| `isAlert(): bool` | `state` が `status` で、status が `cancelled` / `delayed` / `suspended` |
| `isDeparted(DateTimeInterface $now): bool` | `departureAt < $now` かつ（status が `operating` または運航予定）。`isAlert()` なら常に false |
| `checkedAtDiffersFrom(?DateTimeInterface $common): bool` | 行に確認時刻を出すかの判定（分単位で比較） |

### PortAlert（新規）

異常の要約の1項目。

| フィールド | 型 | 説明 |
|---|---|---|
| `date` | `DateTimeImmutable` | 出港日 |
| `direction` | `RouteDirectionEnum` | 方向 |
| `port` | `Port` | 出発港 |
| `arrivalPortName` | `string` | 到着港名 |
| `entry` | `PortBoardEntry` | 該当の便（ステータス・会社・時刻） |

- `anchor(): string` … `r-{Y-m-d}-{direction}-{portId}`（一覧の行の `id` と同じ）

### PortAlertSummary（新規）

| フィールド | 型 | 説明 |
|---|---|---|
| `alerts` | `list<PortAlert>` | 表示する項目（絞り込み条件に合うもの）。日付→方向→寄港順 |
| `hiddenCount` | `int` | 絞り込みの外にある異常の件数（FR-013） |
| `hasData` | `bool` | ボードにデータがあるか。false なら「異常なし」を出さない（FR-011） |

**作り方**: `PortAlertSummaryBuilder::build(PortBoard $fullBoard, PortFilter $filter): PortAlertSummary`。全港のボードを走査し、`isAlert()` のエントリーを集めて、絞り込み条件で `alerts` と `hiddenCount` に分ける。

### CompanyDay（新規、会社別ページ用）

| フィールド | 型 | 説明 |
|---|---|---|
| `date` | `DateTimeImmutable` | 日付 |
| `state` | `CompanyDayStateEnum` | `services`（便あり）/ `no_service`（便なし）/ `no_info`（情報なし） |
| `routeSummaries` | `list<array{route: Route, status: OperationStatus}>` | 航路単位の要約行。情報がある航路だけ |
| `board` | `?PortBoardDay` | その会社の便の行。`state` が `services` のときだけ入る |

**state の決め方**:
- `forCompany()` の後に行が1つ以上ある → `services`
- 行は無いが、その日その会社の `departure_statuses` に `no_service` の行がある → `no_service`
- その日その会社の `departure_statuses` が1行も無い → `no_info`

`CompanyDayStateEnum` は `app/src/Enum/` に置く（新規）。

---

## リポジトリ（読み取りのみ）

| メソッド | 内容 |
|---|---|
| `DepartureStatusRepository::findLatestCheckedAtByCompany(DateTimeImmutable $today): array` | 有効な会社・有効な航路で、`departure_date >= $today - 1日` の行について、会社ごとの `MAX(checked_at)`。`[companyId => DateTimeImmutable]`。`idx_departure_date_port` が効く。結果に出てこない会社は呼び出し側（`SiteExtension`）で古い扱いにする |
| `FerryCompanyRepository::findBoardCompanies(): list<FerryCompany>` | 有効で、方向のある有効な航路を持つ会社（情報の古さの判定の基準）。新規 |
| `OperationStatusRepository::findUpcomingByCompany(FerryCompany $company, int $days): array` | 今日〜`$days-1` 日先の、その会社の有効な航路の行。`[Y-m-d => list<OperationStatus>]` |
| `OperationStatusRepository::findRecentByCompany()` | **削除**（会社別ページでしか使っていない）。`OperationStatusRepositoryTest` の該当テスト2件も削除 |

## Cookie

| 名前 | 値 | 属性 |
|---|---|---|
| `port_filter` | `port={id}&dir={down|up}`（クエリ文字列の形） | 有効期限 1 年、`Path=/`、`SameSite=Lax`、`HttpOnly`（JS から読まない）。書くのはフォームの「保存」（POST・CSRF トークンあり）のときだけ、消すのはフォームの「保存を解除」（同）と値が不正なときだけ |
