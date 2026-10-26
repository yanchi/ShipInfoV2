# Research: 臨時便がある日の会社カードのバッジ

## R1: バッジを「スケジュール変更」にする場所

**Decision**: `StatusController` で航路ごとのバッジ（今の `routesDepartingMidway()`）を組み立てた後に、臨時便がある航路を「changed」に変える処理を足す。配列とテンプレートの変数は `routeBadges` に名前を変える（航路単位が便なしでない航路も入るため）。

変える条件（FR-001）：今日その方向に `firstExtraDepartureOf()` が返す臨時便があり、ふだんのバッジが次のどちらか。

| ふだんのバッジの出どころ | 条件 |
|---|---|
| 航路単位（`routeBadges` に無い航路） | 航路単位の状態が `Operating` |
| `midwayDisplay()` の `badge` | `status` が `Operating`、または `state` が `Scheduled` |

`changed` のときテンプレートは今の「▲ スケジュール変更」のリンク（会社詳細ページへ）を出し、注意書きは出さない（今の `changed` と同じ。FR-005）。臨時便の1行はそのまま出る（FR-003）。

**Rationale**: 判定に使う材料（航路単位の状態・`midwayDisplay()` の結果・`firstExtraDepartureOf()`）は、今のコントローラーに全部そろっている。テンプレートの分岐（`changed` / `badge` / 航路単位）は変えずに済む。

**Alternatives considered**:
- Twig 側で `routesWithExtra` を見て分岐する：条件がテンプレートとコントローラーに分かれ、テストしにくい。却下
- `midwayDisplay()` の中で臨時便を数える：航路単位から決まる航路（今日の例はこちら）を拾えない。却下

## R2: 「臨時便がある」の判定

**Decision**: 今の臨時便の1行と同じ `PortBoardDay::firstExtraDepartureOf()`（今日・その方向・状態 `Extra`・出港時刻あり。出港済みも含む）を使う。

**Rationale**: バッジと1行が食い違わない（spec Assumptions）。出港後も戻さない（Clarifications）。抜粋で欠航などになった臨時便の行は状態が `Extra` でないので数えない（spec Edge Cases）。

## R3: 「抜港あり」の判定

**Decision**: `PortBoard` に、その会社・その方向について「今日を出る臨時便のうち、抜港があるものがあるか」を返すメソッドを足す。

1. ボードの全日付から、その会社・その方向の状態 `Extra` のエントリーを集める（港の行の並び＝寄港順の位置と一緒に）
2. 船ごとに出港時刻で並べ、寄港順の位置が前より進まなくなったところで切る。切った1まとまりを1回の運航とする
3. 今日を出るエントリーを含む運航だけを見る
4. その運航の最初と最後の位置のあいだにある港のうち、運航の出港日の範囲で、同じ会社・同じ船のエントリーが次のどちらでもない港があれば「抜港あり」
   - 状態 `Extra`
   - 走る状態（運航予定・通常運航・条件付遅延・不明）。12 の「便検索の行とぶつかった港」は便検索（定期便）の行が残るので、寄港として数える
5. 欠航・運休・抜港・行なし・便なし・情報なしは寄らない

`PortBoardExtraDeparture` に `bool $skipsPorts`（既定 `false`）を足し、`routesWithExtra()` で詰める。テンプレートは `{% if extra.skipsPorts %}・抜港あり{% endif %}`。

**Rationale**:
- 臨時便は寄らない港の行を作らない（マルエー 12 の FR-006、マリックス 13 の FR-003）。行が無いことで抜港と分かり、会社を問わない
- 日をまたぐ運航（今日 22:00 発・翌日に次の港）は、ボードの4日分から同じ船の続きを拾える。前日に始発港を出た運航（10/27 の名瀬 03:50）は、ボードに前日の行が無いので今日の最初の港からになる。それより前の港は数えない（spec Edge Cases）
- 寄港順の位置はボードの行の並び（`findBoardStops()`）。今の4航路は2社とも同じ港・同じ順なので、ボードの並びをそのまま使える
- マリックス 9/7 上り（那覇・名瀬が臨時便、本部〜亀徳は定期便の欠航の行）は、本部〜亀徳が欠航なので抜港。spec の US2-3 どおり

**Alternatives considered**:
- 行の詳細の「寄港いたしません」を読む：マルエーにしかない。マリックスは h2・h4 の文で、書き方が決まっていない。却下
- `route_stops` を会社ごとに読む：今は2社とも同じ港の並びなので不要。会社ごとに並びが変わる航路が来たら考える

## R4: 通知メール

**Decision**: `IrregularService::statusText()` の「通常運航（臨時便あり）」を「スケジュール変更（臨時便あり）」にする。「スケジュール変更」はトップのバッジの文言と同じ。ほかの分岐は変えない（FR-006）。

**Rationale**: 1行だけの変更。件名・送る条件・港の並びは変えない。

## R5: 今あるテストへの影響

FR-001 で振る舞いが変わるので、次のテストの期待を書き換える（決まりを変えたことはテストの名前・説明にも書く）。

| テスト | 今の期待 | 変更後 |
|---|---|---|
| `StatusControllerTest::testIndexCardOriginExtraWithMidwayRegularKeepsRegularBadge` | ✓ 通常運航 | ▲ スケジュール変更 |
| `StatusControllerTest::testIndexCardMidwayRegularPlusExtraKeepsRegularBadge` | ✓ 通常運航・スケジュール変更なし | ▲ スケジュール変更 |
| `IrregularServiceCollectorTest` の「通常運航・全部 Extra」 | 通常運航（臨時便あり） | スケジュール変更（臨時便あり） |

`testIndexCardShowsExtraDepartureUnderRouteBadge`（航路単位が欠航）・`testIndexCardOriginExtraKeepsCancelledBadge`・`testIndexCardMidwayCancelledPlusExtraShowsCancelled` は欠航のままなので変わらない（FR-002）。

臨時便の行が1港だけのテストは、運航の最初と最後が同じなので「抜港あり」は付かない。今の `◆ 臨時便 名瀬 13:00発` などの完全一致はそのまま通る。
