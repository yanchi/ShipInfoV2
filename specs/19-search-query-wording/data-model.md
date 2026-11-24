# Data Model: 検索語に合わせた会社ページの説明文と船の名前

## ferry_companies（列を足す）

| 列 | 型 | NULL | 説明 |
|---|---|---|---|
| `ship_names` | JSON（文字列の配列） | 可 | 運航している船の名前。並びは表示の順。NULL・空の配列は「無し」 |
| `aliases` | JSON（文字列の配列） | 可 | 検索で使われる会社の別の呼び方を、表示用の文字列で持つ（表記ゆれ・旧社名の注記を含む）。NULL・空の配列は「無し」 |

どちらも `CHECK (… IS NULL OR JSON_TYPE(…) = 'ARRAY')` を付ける（`chk_ferry_companies_ship_names`・`chk_ferry_companies_aliases`）。配列でない JSON が入ると FerryCompany を読むとき（ヘッダーで全ページ）に型エラーになるため。

スクレイパーはこの 2 列を読み書きしない（`scraper/scraper/db/models.py` は変えない。research R2）。

### マイグレーション（`Version20261124000000`）で入れる値

| `scraper_class` | `ship_names` | `aliases` |
|---|---|---|
| `MarueFerry` | `["フェリー波之上", "フェリーあけぼの"]` | `["Aライン（エーライン）"]` |
| `MarixLine` | `["クイーンコーラルクロス", "クイーンコーラルプラス"]` | NULL |

- `UPDATE ferry_companies SET ... WHERE scraper_class = ?`。該当する行が無い環境（テスト DB など）では何もしない
- `down()` は 2 列を消す
- 船が入れ替わったら、新しいマイグレーションで値を直す（quickstart.md）

## FerryCompany エンティティ（`app/src/Entity/FerryCompany.php`）

| プロパティ | 型 | getter | setter |
|---|---|---|---|
| `shipNames` | `?array`（`list<string>`） | `getShipNames(): list<string>`（NULL は `[]`） | `setShipNames(list<string>): static`（掃除して空なら NULL で持つ） |
| `aliases` | `?array`（`list<string>`） | `getAliases(): list<string>`（NULL は `[]`） | `setAliases(list<string>): static`（掃除して空なら NULL で持つ） |

- getter・setter とも同じ掃除をする：文字列以外の要素を捨て、前後の空白を除き、空の要素を捨てる（データに空の要素があっても「運航船：・」のような表示を出さない。FR-007。マイグレーションや手の SQL で入った値も読むため getter でも掃除する）
- 属性：`#[ORM\Column(type: 'json', nullable: true)]`

## バリデーション

- 要素は空でない文字列。重複は入れない（マイグレーションで入れる値で守る。入力画面は無いので Assert は付けない）
- 他社の船・このサイトが扱っていない会社の船は入れない（FR-008。値を決めるときに守る）
