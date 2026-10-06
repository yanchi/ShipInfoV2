# Data Model: 抜港を「抜港」と表示する

**Spec**: [spec.md](spec.md) | **Research**: [research.md](research.md)

DB のテーブル・列は変えない（マイグレーションなし。research R1）。

---

## 1. `OperationStatusEnum`（PHP・Python）

`skipped` を足す。

| 値 | 文言 `label()` | `isIrregular()` | `isAlert()`（PortBoardEntry） | 使う所 |
|---|---|---|---|---|
| operating | 通常運航 | × | × | 航路・港 |
| delayed | 条件付・遅延 | ○ | ○ | 航路・港 |
| **skipped** | **抜港** | **○** | **○** | **港だけ** |
| cancelled | 欠航 | ○ | ○ | 航路・港 |
| suspended | 運休 | ○ | ○ | 航路・港 |
| unknown | 不明 | ○ | × | 航路・港 |
| no_service | 便なし | × | × | 航路・港 |

- `skipped` は `departure_statuses.status`（VARCHAR(32)）にだけ書く。`operation_statuses.status`（MySQL の ENUM）には書かない（FR-011）
- 重さ（航路単位の安全側の判定で使う `_SEVERITY`）には入れない。船ステータスは `skipped` にならないため

---

## 2. `ShipInfo`（marue_ferry.py、メモリ上だけ）

| 項目 | 今 | 変更後 |
|---|---|---|
| `status` | 先頭のタグから | 全タグのうち一番重いもの（research R4） |
| `conditional` | 先頭のタグに「条件付」 | どれか1つのタグに「条件付」 |
| `schedule_changed` | — | **新規**。どれか1つのタグに「遅延」「スケジュール変更」 |

---

## 3. `PortNotice`（port_notice.py、メモリ上だけ）

項目は変えない。`kind="skip"` になる表現を増やす（research R2）。読み取りは括弧書きを取り除いた文で行い、`sentence` には元の文を入れる（research R3）。

---

## 4. 港の行のステータスの決め方

### マルエーフェリー（`_current_voyage_status`）

上から順に最初に当てはまるもの。

1. 船ブロックに無い → `unknown`
2. 船が `cancelled` / `suspended` / `no_service` → 船のステータス（FR-005）
3. その港に `skip` の告知 → **`skipped`**（今は `cancelled`）。詳細は告知の文
4. その港に `change` / `conditional` の告知 → `delayed`（今のまま）
5. 船が `conditional` で、`schedule_changed` でなく、告知がどれかの港にある → `operating`
6. それ以外 → 船のステータス

### マルエーの便検索に日時・便が無い港（research R6）

| 検索結果 | 今 | 変更後 |
|---|---|---|
| マルエーの船の行あり・日時あり | 上の 1〜6 | 変えない |
| マルエーの船の行あり・日時が読めない | 検索全体を失敗（その港・日の行を書かない） | 今の便が同じ航路にあって抜港 → `skipped`（時刻なし）。それ以外 → その行だけ書かない |
| 0件 | `no_service` | 今の便が同じ航路にあり、その港が抜港で、出港日が合う → `skipped`（船名つき・時刻なし）。それ以外 → `no_service` |

出港日 ＝ 今の便の下船日 −（終点の `day_offset` − その港の `day_offset`）

### マリックスライン（`_departures_from_detail`）

| 詳細ページの港 | 今 | 変更後 |
|---|---|---|
| `div.single.no_status`（「―」寄港しません） | `cancelled` | **`skipped`**。詳細は `div.exp`（「寄港しません」）。ただし一覧の便のステータスが `cancelled` / `suspended` なら便のステータス |
| `div.single.cancel` | `cancelled` | 変えない |
| その他 | クラスから | 変えない |

便全体が欠航のときは、詳細ページの港も `cancel` になる（既存の fixture `downstream_cancel.html` は全港 `cancel alert`）。それでも一部の港だけ `no_status` で来たときに抜港へ化けないよう、便のステータス（`voyage_status`）が欠航・運休なら `no_status` の港もそちらにする（FR-005）。

---

## 5. 表示（PortBoardEntry）

- `isAlert()`：`Skipped` を足す → 異常の要約（トップの「欠航・条件付などの便」）に入り、行が強調される（FR-002）
- `isDeparted()`：変更なし。`isAlert()` の行は出港済みにしない仕組みがすでにあるので、抜港も出港済みにならない（FR-009）

## 6. 既存データ

今まで `cancelled` で書いた抜港の行は直さない（spec Edge Cases）。次の実行で、内容が変われば `content_hash` が変わって上書きされる。出港済みで確定した行（マルエーの `freeze_after_departure`）はそのまま。
