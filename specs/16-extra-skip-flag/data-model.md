# Data Model: 臨時便の抜港をスクレイパーが行のフラグで持つ

## departure_statuses（列を足す）

| 列 | 型 | 既定 | 意味 |
|---|---|---|---|
| `skips_ports_after` | BOOLEAN（MySQL は TINYINT(1)）NOT NULL | 0 | 臨時便の行：この港を出たあと、その臨時便の最後の港までに、航路の寄港順にある港のうち寄らない港がある。定期便の行は常に 0 |

- マイグレーション：`app/migrations/Version20261027000000.php`（`ALTER TABLE departure_statuses ADD skips_ports_after TINYINT(1) DEFAULT 0 NOT NULL`）
- Doctrine：`DepartureStatus::$skipsPortsAfter`（`bool`、`options: ['default' => false]`）
- SQLAlchemy：`DepartureStatus.skips_ports_after = Column(Boolean, nullable=False, default=False)`（`make check-schema` で列があるか見る）
- インデックスは足さない（読むのはボードに載せた行だけ）

### 書き方

「最後の港」= 臨時便が寄る港のうち、寄港順で最後のもの（終点まで行けば終点）。行の港を P とすると：

```
skips_ports_after(P) = 寄港順で P より後・最後の港より前に、臨時便が寄らない港がある
```

| 会社 | 寄らない港 | 寄る港 |
|---|---|---|
| マルエー | 寄港順にあって【臨時便】の並びに無い港 | 【臨時便】の並びの港（便検索とぶつかって行を作らない港を含む） |
| マリックス | 詳細ページで `no_status` の港 | 詳細ページで `no_status` でない港（定期便に負けて行を作らない港を含む） |

### 例

**10/27 マルエー下り 波之上**（鹿児島 → 名瀬 → 本部 → 那覇。寄港順：鹿児島・名瀬・亀徳・和泊・与論・本部・那覇）

| 行 | skips_ports_after |
|---|---|
| 鹿児島 10/26 | 1（亀徳・和泊・与論） |
| 名瀬 10/27 03:50 | 1 |
| 本部 10/27 12:00 | 0 |

**終点の1個前を抜く上り**（那覇 → 本部 → 与論 → 和泊 → 亀徳 → 鹿児島。名瀬なし）：那覇〜亀徳の行がすべて 1

**9/27 マリックス上り**（名瀬 → 鹿児島。那覇〜亀徳は `no_status`）：名瀬 0（名瀬より前の `no_status` は数えない）

**9/7 マリックス上り**（那覇 → 名瀬 → 鹿児島。本部〜亀徳は `no_status`）：那覇 1、名瀬 0

### 更新

- `content_hash`：`skips_ports_after` が 1 のときだけ payload に足す（0 の行のハッシュは今と同じ。research R4）
- INSERT・UPDATE とも列を書く。出港済みで確定した行は今までどおり書き直さない

## View（PHP、DB なし）

| クラス | 変更 |
|---|---|
| `PortBoardEntry` | `+ bool $skipsPortsAfter = false`、`- array $noServiceShipNames`、`- isCalling()` |
| `PortBoardDay::firstExtraDepartureOf()` | 対象のエントリーのどれかが `skipsPortsAfter` なら `skipsPorts = true` |
| `PortBoardExtraDeparture` | `- withSkipsPorts()`（`skipsPorts` はコンストラクタで渡す） |
| `PortBoard` | `- extraSkipsPortsOf()`・`isPortIn()`・`callsAt()` |
