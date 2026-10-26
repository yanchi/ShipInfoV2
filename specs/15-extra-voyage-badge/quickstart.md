# Quickstart: 臨時便がある日の会社カードのバッジ

## テスト

```bash
make test-php    # StatusController（バッジ・抜港あり）、PortBoard（抜港の判定）、IrregularService（状況）
make phpstan
make cs-php
make lint-php
```

## ローカルで見る

```bash
make up
```

臨時便がある日のデータが無ければ、`departure_statuses` に今日の下りの臨時便の行（`status = 'extra'`）を名瀬・本部に入れ、航路単位を `operating` にしてトップを開く。

- 下りのバッジが「▲ スケジュール変更」（会社詳細ページへのリンク）
- その下に「◆ 臨時便 名瀬 03:50発・抜港あり」（亀徳・和泊・与論に同じ船の行が無いとき）
- 上りなど臨時便の無い航路は今までどおり

## 通知メール

```bash
make notify-dry-run
```

航路単位が通常運航で通常以外の港の行が臨時便だけの (航路, 日付) は、状況が「スケジュール変更（臨時便あり）」。
