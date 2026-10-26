# Contract: 通知メール（臨時便がある日の状況）

[specs/12-marue-extra-voyages/contracts/notification-mail.md](../../12-marue-extra-voyages/contracts/notification-mail.md) の「状況」の1つだけを変える。テンプレート・件名・送る条件・港の行は変えない。

| 航路×日付 | 通常以外の港の行 | 状況（今） | 状況（変更後） |
|---|---|---|---|
| 通常運航 | 全部 Extra | 通常運航（臨時便あり） | **スケジュール変更（臨時便あり）** |
| 便なし・行なし | 全部 Extra | 臨時便あり | 臨時便あり |
| 通常運航 | Extra 以外もある | 通常運航（途中の港に変更あり） | 通常運航（途中の港に変更あり） |
| 欠航など | あってもなくても | その状態 | その状態 |
