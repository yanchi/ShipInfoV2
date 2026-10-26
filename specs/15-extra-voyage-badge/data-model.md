# Data Model: 臨時便がある日の会社カードのバッジ

**Date**: 2026-10-27 | **Spec**: [spec.md](spec.md)

DB のスキーマ・データは変えない。変えるのは画面に渡すビューの値だけ。

## routeBadges（`StatusController`。今の `routesDepartingMidway`）

`[routeId => ['kind' => 'changed'|'badge', 'state' => ?DepartureDisplayStateEnum, 'status' => ?OperationStatusEnum]]`。

航路がこの配列に無ければ、今までどおり航路単位の状態でバッジを出す。

| 航路単位 | 今日その方向 | kind | 出るバッジ |
|---|---|---|---|
| 便なし | 臨時便以外の行が無く、臨時便がある | badge（Extra） | ◆ 臨時便（13 のまま） |
| 便なし | 途中の港の定期便から `midwayDisplay()` | 今のまま | 今のまま |
| 便なし | 上の結果が `badge` で通常運航・運航予定、かつ臨時便がある | **changed** | **▲ スケジュール変更** |
| 通常運航 | 臨時便がある | **changed** | **▲ スケジュール変更** |
| それ以外 | — | （入れない） | 航路単位の状態 |

「臨時便がある」は `PortBoardDay::firstExtraDepartureOf()` が null でないこと（research R2）。

## PortBoardExtraDeparture

| 項目 | 型 | 内容 |
|---|---|---|
| portName | string | いちばん早い臨時便の港（今のまま） |
| departureAt | DateTimeInterface | その出港時刻（今のまま） |
| **skipsPorts** | **bool（コンストラクタの昇格引数。既定 false）** | **今日を出る臨時便の運航のどれかに抜港がある（research R3）** |

## 臨時便の運航（`PortBoard` の中だけで使う）

ボードの全日付の、その会社・その方向の状態 `Extra` のエントリーを、船名と到着予定（`arrivalAt`）でまとめたもの。船名が空・null、または到着予定が null のエントリーはまとめない（1つで1回の運航）。

| 項目 | 内容 |
|---|---|
| 船 | エントリーの `shipName` |
| 寄港順の位置 | エントリーが入っている行の、方向の行の並びでの添字 |
| 出港日の範囲 | 最初と最後のエントリーの出港日 |
| 到着予定 | エントリーの `arrivalAt`（終点への到着。同じ運航なら同じ） |
| 抜港 | 最初と最後の位置のあいだの港で、出港日の範囲に同じ会社・同じ船の、寄る（`PortBoardEntry::isCalling()`：`Extra` または運航予定・通常運航・条件付遅延・不明）エントリーが無い |
