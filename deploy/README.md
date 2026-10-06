# 本番デプロイ（さくら VPS）

master に push すると、CI（`.github/workflows/ci.yml`）がテストと本番等価スモークテスト（`make verify-prod`）を通したあと、次の順に動く。

1. `build-image`: 本番用イメージを 2 つビルドして GHCR に push する（タグは `latest` とコミット SHA）
   - `ghcr.io/yanchi/shipinfov2/app`（`docker/production/app/Dockerfile`。nginx + php-fpm）
   - `ghcr.io/yanchi/shipinfov2/scraper`（`docker/python/Dockerfile`。開発用パッケージなし）
2. `deploy`: VPS に SSH して `compose.prod.yml` と `docker/mysql/init/*.sql` を転送し、SHA 指定のイメージで `docker compose up -d` する
   - app の entrypoint がマイグレーションを流し、app が healthy になってから scraper が起動する

旧 ShipInfo（`ship.isl-mentor.com`）とは別に、当面は **`v2.ship.isl-mentor.com`** で並べて動かす。ゆくゆくは置き換える（下の「旧 ShipInfo からの切り替え」）。

## 構成

```
インターネット ─ ホストの nginx（80/443・TLS） ─ 127.0.0.1:8002 ─ app（nginx + php-fpm）
                                                                     │
                                                    scraper ──────── mysql（ポート非公開・ボリューム mysql-data）
```

## 初回だけ手でやること

### VPS

```bash
sudo mkdir -p /opt/shipinfo-v2 && sudo chown <デプロイユーザー> /opt/shipinfo-v2
cd /opt/shipinfo-v2
# deploy/.env.production.example を元に値を埋める
vi .env.production && chmod 600 .env.production
```

デプロイユーザーは `docker` を実行できること（docker グループ）。

### DNS と nginx

1. DNS に A レコード `v2.ship.isl-mentor.com → 219.94.240.174`（`ship.isl-mentor.com` と同じ VPS）を足す。ワイルドカードは無いので足さないと引けない
2. `deploy/nginx/shipinfo-v2.conf` の `DOMAIN` を `v2.ship.isl-mentor.com` に置き換えて `/etc/nginx/sites-available/shipinfo-v2` に置き、`sites-enabled/shipinfo-v2.conf` からリンクする（旧版の `shipinfo` と同じ形）
3. `sudo nginx -t && sudo systemctl reload nginx`
4. `sudo certbot --nginx -d v2.ship.isl-mentor.com`

`X-Forwarded-*` を消さないこと。消すと /ports の「この港を保存」が黙って失敗する。

並べて動かす間は、この vhost が `X-Robots-Tag: noindex, nofollow` を付けて検索エンジンに載せない。certbot のあとに `curl -sI https://v2.ship.isl-mentor.com/ | grep -i x-robots-tag` で付いていることを確かめる。

2026-10-03 時点で、1〜4 と下の GitHub の設定・`.env.production` は済んでいる（証明書は certbot が自動で更新する）。デプロイ鍵は ShipInfo 専用（`shipinfo-v2 deploy (GitHub Actions)`。keiei-copilot とは別）。

### GitHub（Settings → Environments → `production`）

| 種類 | 名前 | 値 |
| --- | --- | --- |
| Secret | `DEPLOY_SSH_KEY` | デプロイユーザーの秘密鍵 |
| Secret | `DEPLOY_KNOWN_HOSTS` | VPS のホスト鍵（手元で確かめた `ssh-keyscan <ホスト>` の結果） |
| Secret | `DEPLOY_HOST` | VPS のホスト名か IP |
| Secret | `DEPLOY_USER` | デプロイユーザー |
| Variable | `DEPLOY_URL` | 公開 URL（Environments の画面にリンクが出るだけ） |

## 初回の起動で起きること

`mysql-data` ボリュームが空なので、MySQL が `01_schema.sql` → `02_seed.sql`（フェリー会社・航路マスタ）を流す。そのあと app の entrypoint がマイグレーションを流す。2 回目以降のデプロイでは SQL ファイルは読まれず、マイグレーションだけが流れる。

## 旧 ShipInfo からの切り替え

VPS で動いている他のもの（2026-10-03 時点）:

| ポート | 使っているもの |
| --- | --- |
| 127.0.0.1:8080 | 旧 ShipInfo の Web（shipinfo-symfony）。`ship.isl-mentor.com` の proxy_pass 先 |
| 0.0.0.0:8000 | 旧 ShipInfo のスクレイパー（shipinfo-python）。外部に公開されている |
| 127.0.0.1:8001 | keiei-copilot |
| 127.0.0.1:8081 | isl-mentor.com |
| 127.0.0.1:3000 | ai-task-manager |

V2 に置き換えるときは:

0. V1 の本番の環境変数から GA の測定 ID（`GOOGLE_ANALYTICS_ID`）を確認し、V2 の `/opt/shipinfo-v2/.env.production` に `GOOGLE_ANALYTICS_ID=<V1 と同じ ID>` を足す。`v2.ship.isl-mentor.com` で並べている間は**入れない**（V2 のアクセスが V1 の計測に混ざるため）
1. `/etc/nginx/sites-available/shipinfo`（`ship.isl-mentor.com`）の `proxy_pass` を `127.0.0.1:8080` → `127.0.0.1:8002` に変えて、`X-Forwarded-Host`・`X-Forwarded-Port` も足す（`shipinfo-v2.conf` と同じヘッダーにする）
2. `.env.production` の `DEFAULT_URI` を `https://ship.isl-mentor.com` にして、`docker compose -f compose.prod.yml --env-file .env.production up -d`
3. `sudo nginx -t && sudo systemctl reload nginx`。戻すときは proxy_pass を 8080 に戻すだけ
   切り替え後に確かめること: `https://ship.isl-mentor.com/details/today` が `/ports` に 301 で移る／`/robots.txt`・`/sitemap.xml` のホストが `https://ship.isl-mentor.com`／GA のリアルタイムレポートで計測が続いている
   `X-Robots-Tag`（noindex）は `shipinfo-v2.conf` にしか無いので、`ship.isl-mentor.com` では付かず検索エンジンに載る。旧版の vhost に写さないこと
4. 落ち着いたら旧 ShipInfo のコンテナ（`shipinfo` プロジェクト。8000 の外部公開もこれで消える）を止め、`v2.ship.isl-mentor.com` を `ship.isl-mentor.com` へのリダイレクトにするか消す

旧版と V2 は DB が別（旧版は `shipinfo-db-1`、V2 は `shipinfo-v2-mysql-1`）。過去の運航情報を持ち越すなら、切り替えの前に移す方法を決めること。

## 運航の変更の通知メール

app コンテナの supercronic が、日本時間の 1・6・15 時に `app:notify-irregular-statuses` を www-data で動かす（`docker/production/app/crontab`）。今日〜3日先に通常運航以外の便があれば、運営者に `【ShipInfo V2】非通常運航ステータスを検出 (N件)` を 1 通送る。同じ回は `notification_runs` の一意キーで 1 通まで（specs/8-schedule-change-mail）。

### 設定（`.env.production`）

```
# ユーザー名・パスワードに記号があれば URL エンコードする（@ → %40、: → %3A、/ → %2F など）
MAILER_DSN=smtp://USER:PASSWORD@isl-mentor.sakura.ne.jp:587
NOTIFY_FROM=...
NOTIFY_TO=a@example.com,b@example.com
```

どれかが空なら、送らずに `not_configured` の警告を出すだけ（サイト・スクレイパーには影響しない）。入れたら `docker compose -f compose.prod.yml --env-file .env.production up -d app` で app を作り直す。

`not_configured` も「処理済みの回」として記録され、同じ回は送り直さない。設定は確認時刻より前に入れること。

### SMTP の確認と TLS の証明書

設定を入れたら、自分宛てに 1 通送って確かめる。`mailer:test` は `notification_runs` を使わないので、その日の回を消費しない。

```bash
cd /opt/shipinfo-v2
docker compose -f compose.prod.yml exec app php bin/console mailer:test 自分のアドレス --from="<NOTIFY_FROM と同じ>" --subject="【ShipInfo V2】SMTP 確認"
```

**SMTP のホストは `isl-mentor.sakura.ne.jp`**（`mail.isl-mentor.com` ではない）。どちらも同じさくらのレンタルサーバー（133.242.249.170）だが、証明書が共用の `*.sakura.ne.jp` なので、`mail.isl-mentor.com` では `subjectAltName did not match` で落ちる（2026-10-06 に確認。V1 は検証をオフにしていたので気づかなかった）。ユーザー名はメールアドレスなので `@` を `%40` にする。

TLS の証明書は検証する（Symfony の既定）。`certificate verify failed` などで落ちたら、まず DSN のホスト名を証明書の名前に合わせる。どうしても通らないときだけ DSN に `?verify_peer=0` を足し、その理由をここに書くこと。

### 確認の仕方

```bash
docker compose -f compose.prod.yml logs app | grep -E '確認時刻|件を送りました|送信に失敗|未設定'
docker compose -f compose.prod.yml exec mysql sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" mysql -u"$MYSQL_USER" "$MYSQL_DATABASE" -e "SELECT * FROM notification_runs ORDER BY id DESC LIMIT 5"'
```

`result` が `pending` のまま残っている回は、送信の途中でプロセスが落ちた回（再送はしない）。行は 90 日で消える。

**本番で手で動かすときは必ず `--dry-run` を付ける。** 付けないと今日のその回を確保するので、確認時刻より前に動かすと、cron の本来の回が「処理済み」になって送られない。

```bash
docker compose -f compose.prod.yml exec app su -s /bin/sh www-data -c 'php bin/console app:notify-irregular-statuses --slot=6 --dry-run'
```

### supercronic の更新

Dependabot の対象外。[リリースのページ](https://github.com/aptible/supercronic/releases)で新しい版と `supercronic-linux-amd64` の SHA-1 を確かめ、`docker/production/app/Dockerfile` の `SUPERCRONIC_VERSION`・`SUPERCRONIC_SHA1SUM` を直す。SHA-1 はダウンロードしたバイナリで `shasum -a 1` を取り、リリースノートの値と一致することも確かめる。

## ロールバック

```bash
cd /opt/shipinfo-v2
export APP_IMAGE=ghcr.io/yanchi/shipinfov2/app:<戻したいコミットの SHA>
export SCRAPER_IMAGE=ghcr.io/yanchi/shipinfov2/scraper:<同じ SHA>
docker compose -f compose.prod.yml --env-file .env.production up -d
```

GHCR が private なので、pull するには `docker login ghcr.io`（`read:packages` の PAT）が要る。VPS に直近 5 世代のイメージが残っていれば pull せずに戻せる。

マイグレーションは戻らない。DB の形を変えたコミットより前に戻すときは、先に `doctrine:migrations:migrate prev` などで DB を戻すこと。

## やってはいけないこと

- `docker compose -f compose.prod.yml down -v`: 運航情報がすべて消える
- `docker image prune -a`: 同居している他サービスのロールバック用イメージまで消える
