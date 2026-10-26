# Research: 臨時便の抜港をスクレイパーが行のフラグで持つ

## R1: 何を記録するか

**Decision**: `departure_statuses` に `skips_ports_after`（BOOLEAN、NOT NULL、既定 false）を足す。臨時便の港の行ごとに「この港を出たあと、その臨時便の最後の港までに、航路の寄港順にある港のうち寄らない港があるか」を書く（spec FR-001）。

- 最後の港：臨時便が寄る港のうち寄港順で最後のもの。終点まで行く便なら終点（ボードの行に無い港も含む。終点の1個前の港を見落とさない）
- 「寄らない」は会社ごとに公式の書き方で決める（R2・R3）
- 定期便の行は常に false（FR-005）

**Rationale**:
- 行ごと（その港を出たあと）にすると、Web は今日の臨時便の行だけを見ればよい。前日に通った港の抜港で今日「抜港あり」と出ない（15 の「今日の最初の港から見る」と同じ。spec Assumptions）
- 今日出て明日に次の港を出る運航も、今日の行に明日以降の抜港が入る

**Alternatives considered**:
- 運航ごとの1値（運航の全行に同じ値）：前日に通った港だけを抜いた運航で、今日の行にも「抜港あり」と出る。却下
- 抜く港の ID を JSON で持つ：カードに港名は出さない（15 の Out of Scope）。使い道の無い値を持たない。却下
- 寄らない港に状態「抜港」の行を作る：12 の FR-006・13 の FR-003 で寄らない港の行を作らないと決めた理由（定期便の時刻・別の日付が残る、会社詳細に行が増える）がそのまま残る。却下

## R2: マルエーフェリー

**Decision**: `MarueFerry._extra_records()` で、臨時便（`ExtraVoyage`）の `stops[:-1]` の各港について、航路の寄港順（`_get_stops()[route_id]`）で「その港より後・`stops[-1]`（終点の入港）より前」にあり、`voyage.stops` の港に無い港があれば `skips_ports_after = True`。

- 判定は `ExtraVoyage` のメソッド（またはスクレイパーの小さい関数）にして、`_extra_status()` が欠航などを返した行にも同じ値を書く（spec Assumptions。Web は状態が Extra の行だけ読む）
- 便検索の行とぶつかって作らない港（`_note_extra_conflict`・`recorded`）も `voyage.stops` に入っているので寄港のまま（FR-004）
- `skip_note`（「※ …寄港いたしません。」）は使わない。港の並びのほうが確実（文が無い臨時便もありうる）

**Rationale**: `_build_extra_voyage()` は港が寄港順に並んでいることを確かめて読んでいる（`order.get(port.id, -1) <= last_order` なら読めない）。なので、寄港順にあって並びに無い港＝寄らない港。

## R3: マリックスライン

**Decision**: `MarixLine._parse_detail_departures()`（詳細ページから行を作るところ）で、臨時便のとき `no_status` の港の ID を集める（今は `continue` で捨てている）。寄る港（`by_port` に入った港。終点を含む）の寄港順で最後の位置を「最後の港」とし、各行について「その港より後・最後の港より前」に `no_status` の港があれば `skips_ports_after = True`。

- 詳細ページに出てこない港（`detail_port_not_in_stops`・ページに無い）は寄らない港に数えない（spec Edge Cases。分からないときは言わない）
- 運航の最初の港より前の `no_status`（名瀬発の臨時便の鹿児島など）は、どの行より前なので数えない
- `_resolve_extra_conflicts()` で定期便に負けて落とした臨時便の行の港は `by_port` にあるので寄港（FR-004）
- 定期便（`is_extra` が False）の行は false。定期便の `no_status` は今までどおり状態 `skipped` の行

**Rationale**: 寄らない港は詳細ページに `no_status` と書かれる（13 の R3）。

## R4: 既存行の書き直しとハッシュ

**Decision**: `BaseScraper._departure_hash()` の payload に、`skips_ports_after` が True のときだけ要素を足す。`_upsert_departures()` は INSERT・UPDATE のどちらでも `skips_ports_after` を書く。

- 既にある行は列の既定 false。次のスクレイプで True になる臨時便の行だけハッシュが変わり、書き直される（FR-010）
- False の行（定期便・抜港の無い臨時便）はハッシュが今と同じなので `scraped_at` は進まない（SC-004）
- 出港済みで確定した行（`freeze_after_departure`）は書き直さない。入れた日に出港済みの臨時便の行は false のまま（spec Edge Cases）

**Alternatives considered**:
- payload に常に足す：全部の行のハッシュが変わり、最初の回に全行の `scraped_at` が進む。却下
- マイグレーションで既存行を計算して埋める：寄らない港の情報は DB に無いので計算できない

## R5: Web

**Decision**:

- `DepartureStatus`（Entity）に `skipsPortsAfter`（bool、既定 false）
- `PortBoardEntry` に `public bool $skipsPortsAfter = false`。`PortBoardBuilder` で詰める
- `PortBoardDay::firstExtraDepartureOf()` が、今見ている臨時便のエントリー（今日・その方向・状態 Extra・出港時刻あり）のどれかが `skipsPortsAfter` なら `skipsPorts = true` の `PortBoardExtraDeparture` を返す（FR-006）
- 消すもの（FR-008）：`PortBoard::extraSkipsPortsOf()`・`isPortIn()`・`callsAt()`、`PortBoardEntry::isCalling()`・`$noServiceShipNames`、`PortBoardBuilder` の `$hidden`、`PortBoardExtraDeparture::withSkipsPorts()`、`StatusController::routesWithExtra()` の `$portIds` と `extraSkipsPortsOf` の呼び出し

**Rationale**: 「臨時便の1行」と「抜港あり」が同じエントリーの集まりから決まり、食い違わない。ボードの他の日・他の行を見ない。

## R6: 15 の文書

**Decision**: 15 の `contracts/ui-status.md`（臨時便の1行の「抜港あり」の決め方）と `research.md` の R3 に「16-extra-skip-flag で変更」の注記とリンクを足す（FR-011）。本文は残す（経緯として読めるように）。
