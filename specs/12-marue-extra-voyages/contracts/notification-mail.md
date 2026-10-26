# Contract: 通知メール（臨時便を足す）

[specs/8-schedule-change-mail/contracts/notification-mail.md](../../8-schedule-change-mail/contracts/notification-mail.md) のまま。テンプレート・件名・送信ルールは変えない（抜港を足したとき＝9-marue-port-skip と同じ）。

変わるのは enum から決まる2点だけ（research R9）。

| 項目 | 変更 |
|---|---|
| 対象の港の行 | `OperationStatusEnum::irregularCases()` に `extra` が入る → `findIrregularBetween()` が臨時便の行も返す。臨時便の行しか無い回も送る |
| 港の行の状態のラベル | `port.status.label()` が「臨時便」 |
| 状況（`IrregularService::statusText()`） | 航路×日付が通常運航以外でなく、港の行が全部 Extra のとき：航路が通常運航なら「通常運航（臨時便あり）」（→ 15-extra-voyage-badge で「スケジュール変更（臨時便あり）」に変更。臨時便とそれ以外が混ざる日は「スケジュール変更（途中の港に変更あり）」。[contracts/notification-mail.md](../../15-extra-voyage-badge/contracts/notification-mail.md)）、それ以外（便なし・行なし）は「臨時便あり」。港の行に Extra 以外も混ざるときは今までどおり「〜（途中の港に変更あり）」。航路×日付が欠航などのときは今までどおりその状態 |

## 例（保存版の 10/28 上り・マルエー）

```
  会社名: マルエーフェリー
  運航日: 2026-10-28（水）
  方向　: 上り（鹿児島行き）
  状況　: 臨時便あり
  港　　:
    - 那覇 05:00発 フェリー波之上：臨時便
    - 本部 07:20発 フェリー波之上：臨時便
    - 与論 10:10発 フェリー波之上：臨時便
    - 和泊 12:40発 フェリー波之上：臨時便
    - 亀徳 15:00発 フェリー波之上：臨時便
    - 名瀬 19:20発 フェリー波之上：臨時便
```

（10/28 の上りは那覇の便検索が空＝航路×日付が便なしなので「臨時便あり」）

- 下りの臨時便（10/26 鹿児島・10/27 名瀬・本部）は、寄港しない港の文が港ごとに（　）で付く。同じ文が並ぶが、テンプレートは変えない（港の行の詳細をそのまま出す今の決まり）
