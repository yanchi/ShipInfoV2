# Contract: 通知メール（抜港を足す）

[specs/8-schedule-change-mail/contracts/notification-mail.md](../../8-schedule-change-mail/contracts/notification-mail.md) のまま。テンプレート・件名・送信ルールは変えない。

変わるのは enum から決まる2点だけ（research R9）。

| 項目 | 変更 |
|---|---|
| 対象の港の行 | `OperationStatusEnum::irregularCases()` に `skipped` が入る → `findIrregularBetween()` が抜港の行も返す |
| 港の行の状態のラベル | `port.status.label()` が「抜港」 |

## 例（保存版の 10/6 下り・マルエー）

```
  会社名: マルエーフェリー
  運航日: 2026-10-06（火）
  方向　: 下り（那覇行き）
  状況　: 通常運航（途中の港に変更あり）
  港　　:
    - 和泊 フェリー波之上：抜港（10月6日(火)和泊港 抜港）
    - 与論 フェリー波之上：抜港（10月6日(火)与論港 抜港）
```

（航路単位・ほかの港の行は、その時点の DB の内容による。上は港の行の書き方の例）

- 航路×日付の「状況」には「抜港」は出ない（航路単位は抜港にならない。FR-011）
- 前回「欠航」・今回「抜港」の行に特別な印は付けない（spec Assumptions）
