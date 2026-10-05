# Contract: `app:notify-irregular-statuses`

確認時刻に supercronic から呼ばれる Console コマンド（research R2・R4）。

```
php bin/console app:notify-irregular-statuses [--slot=1|6|15] [--dry-run]
```

## オプション

| オプション | 内容 |
|---|---|
| （なし） | 今の時刻（日本時間）から回を決める。1:00・6:00・15:00 から 10 分以内でなければ何もしない |
| `--slot=N` | 回を N 時（1・6・15 のどれか）に決める。時刻の窓は見ない。それ以外の値はエラー（終了コード 2） |
| `--dry-run` | 件名・本文を標準出力に出すだけ。回を確保しない・送らない・行を消さない |

> **本番で手で動かすときは必ず `--dry-run` を付ける。** `--dry-run` 無しの `--slot` は今日のその回を確保する。確認時刻より前に動かすと、cron の本来の回が「処理済み」になり、その時刻の最新の状態が送られない（research R4）。

## 処理の順番

1. 回を決める（窓の外なら「確認時刻ではありません」を出して終了コード 0）
2. `--dry-run` でなければ `notification_runs` に `(今日, slot, pending)` を INSERT。一意キーに当たったら「この回は処理済みです」を出して終了コード 0
3. 通常運航以外の便を集める（data-model §2）
4. 0 件 → `none`。終了コード 0
5. 設定（`MAILER_DSN`・`NOTIFY_FROM`・`NOTIFY_TO`）が足りない → 警告を出し `not_configured`。終了コード 0
6. 送る → `sent`・`item_count`。終了コード 0
7. 送信で例外 → エラーを出し `failed`・`error_message`。終了コード 1
8. 90 日より古い `notification_runs` を消す

## 出力（標準出力・標準エラー。supercronic 経由で docker logs に出る）

| 場面 | レベル | 文言の例 |
|---|---|---|
| 窓の外 | info | `確認時刻ではありません（現在 03:12）` |
| 処理済み | info | `2026-10-07 6時の回は処理済みです` |
| 0 件 | info | `2026-10-07 6時：通常運航以外の便はありません` |
| 設定なし | warning | `NOTIFY_TO が未設定のためメールを送りませんでした` |
| 送った | info | `2026-10-07 6時：3件を送りました（宛先 2）` |
| 失敗 | error | `メールの送信に失敗しました: <例外のメッセージ>` |

ログ・`error_message` に DSN・パスワード・宛先のアドレスは出さない（宛先は件数だけ）。

## 起動（本番）

`docker/production/app/crontab`：

```
# 日本時間（TZ=Asia/Tokyo）。運航に変更がある便を知らせる（specs/8-schedule-change-mail）
0 1,6,15 * * * php /var/www/html/bin/console app:notify-irregular-statuses --no-interaction
```

supervisord の `[program:supercronic]` で www-data として `supercronic /etc/crontab` を動かす（bin/console を root で動かさない。entrypoint と同じ理由）。

## Make（開発）

| ターゲット | 中身 |
|---|---|
| `make notify-dry-run` | `bin/console app:notify-irregular-statuses --slot=6 --dry-run` |
| `make notify SLOT=6` | `bin/console app:notify-irregular-statuses --slot=$(SLOT)`（Mailpit に送る。`make up-tools` が前提） |
