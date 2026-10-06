# Quickstart: 運航に変更がある便をメールで知らせる

## 開発環境で中身を見る（送らない）

```bash
make up
make migrate
make notify-dry-run        # 件名と本文が出る。回は確保しない
```

欠航のデータが無ければ、phpMyAdmin（`make up-tools`）などで今日〜3日先の `operation_statuses` か `departure_statuses` の `status` を `cancelled` にして試す。

## 開発環境で送ってみる（Mailpit に届く）

```bash
make up-tools              # phpMyAdmin と Mailpit も起動
make notify SLOT=6
open http://localhost:8025 # Mailpit。件名が【ShipInfo V2】で始まる
```

同じ日に `make notify SLOT=6` をもう一度動かすと「処理済み」になり、2 通目は届かない（FR-009）。
もう一度試すときは `notification_runs` の今日の行を消す。

## 設定なし・送信失敗を確かめる（US3）

```bash
# 設定なし：NOTIFY_TO を空にする → 警告が出て結果は not_configured
docker compose exec -e NOTIFY_TO= php bin/console app:notify-irregular-statuses --slot=1

# 送信失敗：繋がらない DSN → エラーが出て結果は failed、終了コード 1
docker compose exec -e MAILER_DSN=smtp://127.0.0.1:1 php bin/console app:notify-irregular-statuses --slot=15
```

どちらのあとも `make scraper-run` とトップページは普段どおり動く（別プロセス）。

## テスト

```bash
make test-php    # 判定・まとめ方・本文・回の確保・設定なし・失敗
make phpstan
make lint-php    # schema:validate で notification_runs のマッピングも見る
make verify-prod # 本番イメージで supercronic が起動しているか・TZ も確かめる
```

## 本番に出すとき

1. VPS の `/opt/shipinfo-v2/.env.production` に足す（V1 の `.env` の SMTP・宛先と同じもの）

   ```
   # ユーザー名・パスワードに記号があれば URL エンコードする（@ → %40 など）
   MAILER_DSN=smtp://USER:PASSWORD@SMTP_HOST:587
   NOTIFY_FROM=...
   NOTIFY_TO=a@example.com,b@example.com
   ```

2. VPS から本番の SMTP で送れるか確かめる。V1 は証明書の検証をオフにしていたので、同じサーバーでも検証で落ちることがある。`mailer:test` は `notification_runs` を使わないので、その日の回を消費しない

   ```bash
   # PR2 のデプロイ後（compose.prod.yml が MAILER_DSN などを app に渡すようになってから）
   docker compose -f compose.prod.yml exec app php bin/console mailer:test 自分のアドレス --from="<NOTIFY_FROM と同じ>" --subject="【ShipInfo V2】SMTP 確認"
   ```

   PR1 の時点の `compose.prod.yml` は設定を app に渡さないので、この確認は PR2 のデプロイ後に行う（`.env.production` に入れただけでは `null://null` のまま）。落ちたら deploy/README の証明書の節を見る

3. master に push（CI がデプロイ）
4. 次の確認時刻のあとに確かめる

   ```bash
   docker compose -f compose.prod.yml logs app | grep -E '確認時刻|件を送りました|送信に失敗'
   docker compose -f compose.prod.yml exec mysql sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" mysql -u"$MYSQL_USER" "$MYSQL_DATABASE" -e "SELECT * FROM notification_runs ORDER BY id DESC LIMIT 5"'
   ```

   `result` が `pending` のまま残っている回は、送信の途中でプロセスが落ちた回（再送はしない）。

   本番で手で中身を見るときは必ず `--dry-run` を付ける（付けないと、確認時刻より前ならその回を先に取ってしまう）。

5. 並行運用の 1 週間、V1（`【ShipInfo】`）と V2（`【ShipInfo V2】`）の同じ回を比べる（SC-004）。V1 は 0 時、V2 は 1 時に届く点に注意
