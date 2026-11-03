# Data Model: 港ごとのページと、検索で選ばれるタイトル・説明文

## ports（列を足す）

| 列 | 型 | 説明 |
|----|----|------|
| `slug` | `VARCHAR(32) NOT NULL`、UNIQUE | 港のページの URL に使う名前。英小文字で始まり、英小文字・数字・`-` だけ。一度決めたら変えない |
| `display_name` | `VARCHAR(64) NULL` | 港の呼び名（タイトル・見出し・説明文に使う）。NULL なら `name` を使う |

マイグレーション（`Version20261104000000`）：列を NULL 可で足す → 7 港に値を入れる → `slug` を NOT NULL にして UNIQUE を付ける。

| name | slug | display_name |
|------|------|--------------|
| 鹿児島 | `kagoshima` | NULL |
| 名瀬 | `naze` | 奄美大島（名瀬港） |
| 亀徳 | `kametoku` | 徳之島（亀徳港） |
| 和泊 | `wadomari` | 沖永良部島（和泊港） |
| 与論 | `yoron` | 与論島（与論港） |
| 本部 | `motobu` | 沖縄（本部港） |
| 那覇 | `naha` | 沖縄（那覇港） |

- 7 港以外の港が DB にあった場合（ローカルで手で足したなど）は、`slug` を `port-<id>` で埋めてから NOT NULL にする（マイグレーションを失敗させない）
- down: 2 列を消す

## Port（エンティティ）

- `slug`（string）・`displayName`（?string）を足す
- `getDisplayName(): string` — `displayName ?? name`
- スクレイパーの `Port` モデルには足さない（読み書きしないので要らない。research R1）

## PortFilterResolution（ビュー）

- `redirectTo` を GET の 301 転送にも使う（今は POST の 303 だけ）。GET `/ports` で `redirectTo` があれば、コントローラーが 301 を返す

## PortFilter（ビュー）

- 変えない。Cookie・フォームの値は今までどおり港の ID（`port=<id>&dir=<down|up>`）
