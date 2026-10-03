#!/usr/bin/env bash
#
# 本番等価スモークテスト。
#
# 本番用イメージをビルドして compose.prod.yml を実際に起動し、本番でしか通らない経路を通す。
# PHPUnit は dev の構成（APP_ENV=test）で動くので、次のような不具合は拾えない:
#   - 本番イメージに入れ忘れた拡張・ファイル、prod でだけ読む設定の誤り
#   - 空の DB に 01_schema.sql → 02_seed.sql → マイグレーションの順で流せない
#   - trusted_proxies が無く、https の裏で /ports の「この港を保存」が黙って失敗する
#   - 再デプロイ（down → up）で DB が消える
#
# どの変更が本番構成に効くかはファイル名では決められない（framework.yaml の 1 行でも壊れる）ので、
# 全 PR で動かす。
#
set -euo pipefail

cd "$(dirname "$0")/.."

# 本番（shipinfo-v2）とは別のプロジェクト名にする。
# 取り違えて本番のボリュームを消さないよう、ここは固定
readonly PROJECT='shipinfo-verify'
readonly PORT="${VERIFY_PORT:-18098}"
readonly APP_IMAGE='shipinfo-app:verify'
readonly SCRAPER_IMAGE='shipinfo-scraper:verify'
# vhost の構文チェック用。latest だと nginx の更新で結果が勝手に変わるので固定する
readonly NGINX_IMAGE='nginx:1.29-alpine'
readonly BASE="http://127.0.0.1:${PORT}"
readonly HOST='verify.example.com'
# ホストの nginx の vhost を動かすコンテナ（6. で使う）
readonly VHOST_CONTAINER="${PROJECT}-host-nginx"
readonly VHOST_PORT="${VERIFY_VHOST_PORT:-18097}"

# readonly と同時に代入すると mktemp の失敗が set -e で拾えないので分ける
ENV_FILE="$(mktemp -t shipinfo-verify-env.XXXXXX)"
readonly ENV_FILE

PASSED=0
FAILED=0

# ---------------------------------------------------------------------------
# 出力
# ---------------------------------------------------------------------------

if [ -t 1 ]; then
    readonly C_OK=$'\033[32m'; readonly C_NG=$'\033[31m'
    readonly C_HEAD=$'\033[1m'; readonly C_OFF=$'\033[0m'
else
    readonly C_OK=''; readonly C_NG=''; readonly C_HEAD=''; readonly C_OFF=''
fi

section() { printf '\n%s── %s%s\n' "$C_HEAD" "$1" "$C_OFF"; }

# ok <説明> <実際> <期待>
ok() {
    if [ "$2" = "$3" ]; then
        printf '  %s✓%s %-44s %s\n' "$C_OK" "$C_OFF" "$1" "$2"
        PASSED=$((PASSED + 1))
    else
        printf '  %s✗%s %-44s %s (期待: %s)\n' "$C_NG" "$C_OFF" "$1" "$2" "$3"
        FAILED=$((FAILED + 1))
    fi
}

# contains <説明> <対象文字列> <含まれるべき部分文字列>
contains() {
    case "$2" in
        *"$3"*)
            printf '  %s✓%s %-44s %s\n' "$C_OK" "$C_OFF" "$1" "$3"
            PASSED=$((PASSED + 1)) ;;
        *)
            printf '  %s✗%s %-44s %s を含まない\n' "$C_NG" "$C_OFF" "$1" "$3"
            printf '      実際: %s\n' "$2"
            FAILED=$((FAILED + 1)) ;;
    esac
}

compose() {
    docker compose -p "$PROJECT" -f compose.prod.yml --env-file "$ENV_FILE" "$@"
}

http_code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

health_of() {
    docker inspect -f '{{.State.Health.Status}}' "${PROJECT}-$1-1" 2>/dev/null || echo 'なし'
}

# healthy になるまで最大 4 分待つ（初回は MySQL の init スクリプトが走る）
wait_healthy() {
    for _ in $(seq 1 80); do
        [ "$(health_of "$1")" = 'healthy' ] && return 0
        sleep 3
    done
    return 1
}

# healthy にならないまま進むと後続が総崩れになり、本当の原因が埋もれる。ここで打ち切る
abort_unhealthy() {
    printf '  %s✗%s コンテナが healthy にならなかった (mysql=%s app=%s)\n' \
        "$C_NG" "$C_OFF" "$(health_of mysql)" "$(health_of app)"
    printf '\n  直近のログ:\n'
    compose logs --tail=40 mysql app 2>&1 | sed 's/^/    /'
    FAILED=$((FAILED + 1))
    exit 1
}

# 応答が空（exec の失敗など）のときは 0 を返す。空のまま数値比較に渡すとエラーが紛れる
mysql_one() {
    local out
    # $MYSQL_* はコンテナの中で展開したいので、シングルクォートのままでよい
    # shellcheck disable=SC2016
    out="$(compose exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" mysql -u"$MYSQL_USER" "$MYSQL_DATABASE" -N -e "$1"' sh "$1" 2>/dev/null \
        | tr -d '[:space:]')" || true
    printf '%s' "${out:-0}"
}

cleanup() {
    local status=$?
    section '後片付け'
    # -v を付けてよいのは、これが使い捨てのプロジェクト（$PROJECT）だから。
    # 本番（shipinfo-v2）で down -v すると運航情報がすべて消える
    docker rm -f "$VHOST_CONTAINER" >/dev/null 2>&1 || true
    compose down -v --remove-orphans >/dev/null 2>&1 || true
    rm -f "$ENV_FILE"
    echo '  完了'
    exit "$status"
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# 準備
# ---------------------------------------------------------------------------

section '準備'

cat > "$ENV_FILE" <<EOF
APP_IMAGE=${APP_IMAGE}
SCRAPER_IMAGE=${SCRAPER_IMAGE}
APP_PORT=${PORT}
APP_SECRET=$(openssl rand -hex 32)
DEFAULT_URI=https://${HOST}
DB_NAME=shipinfo
DB_USER=shipinfo
DB_PASSWORD=$(openssl rand -hex 16)
DB_ROOT_PASSWORD=$(openssl rand -hex 16)
MYSQL_INIT_DIR=${PWD}/docker/mysql/init
EOF
echo '  使い捨ての .env を生成'

# 直前の失敗などで残っている場合に備える
compose down -v --remove-orphans >/dev/null 2>&1 || true

echo '  本番イメージをビルド中...'
docker build -q -f docker/production/app/Dockerfile -t "$APP_IMAGE" . >/dev/null
docker build -q -f docker/python/Dockerfile -t "$SCRAPER_IMAGE" . >/dev/null
echo '  ビルド完了'

# ---------------------------------------------------------------------------
# 1. compose.prod.yml で起動できるか
# ---------------------------------------------------------------------------

section '1. compose.prod.yml による起動'

# scraper は起動しない。起動直後に本物のフェリー会社のサイトを取りに行くので、PR ごとに叩きたくない。
# 代わりに 2. で本番イメージのモデルが DB と合っているかを確かめる
if ! compose up -d mysql app >/dev/null 2>&1; then
    printf '  %s✗%s 起動に失敗した\n' "$C_NG" "$C_OFF"
    compose logs --tail=40 mysql app 2>&1 | sed 's/^/    /' || true
    FAILED=$((FAILED + 1))
    exit 1
fi

wait_healthy app || abort_unhealthy

ok 'mysql が healthy' "$(health_of mysql)" 'healthy'
ok 'app が healthy'   "$(health_of app)"   'healthy'

# ---------------------------------------------------------------------------
# 2. 空の DB からの初期化（01_schema.sql → 02_seed.sql → マイグレーション）
# ---------------------------------------------------------------------------

section '2. DB の初期化'

ok 'マイグレーションが残っていない' \
   "$(compose exec -T app su -s /bin/sh www-data -c 'php bin/console doctrine:migrations:up-to-date --no-interaction' >/dev/null 2>&1 && echo 最新 || echo 未適用あり)" '最新'
ok 'フェリー会社マスタが入っている' \
   "$([ "$(mysql_one 'select count(*) from ferry_companies')" -gt 0 ] && echo あり || echo なし)" 'あり'
ok '港マスタが入っている' \
   "$([ "$(mysql_one 'select count(*) from ports')" -gt 0 ] && echo あり || echo なし)" 'あり'
ok 'スクレイパーのモデルが DB と合っている' \
   "$(compose run --rm --no-deps -T scraper python -m scraper.db.check_schema >/dev/null 2>&1 && echo 一致 || echo 不一致)" '一致'
ok 'MySQL が日本時間' "$(mysql_one 'select @@global.time_zone')" '+09:00'
ok 'PHP が日本時間' \
   "$(compose exec -T app php -r 'echo date_default_timezone_get();' 2>/dev/null | tr -d '[:space:]')" 'Asia/Tokyo'
ok 'prod で動いている（デバッグ無効）' \
   "$(compose exec -T app printenv APP_ENV APP_DEBUG 2>/dev/null | tr -d '[:space:]')" 'prod0'

# ---------------------------------------------------------------------------
# 3. 画面
# ---------------------------------------------------------------------------

section '3. 主要な画面'

ok 'トップ /'          "$(http_code "$BASE/")"         '200'
ok '港別 /ports'       "$(http_code "$BASE/ports")"    '200'
ok '会社別 /company/1' "$(http_code "$BASE/company/1")" '200'
ok '存在しないページは 404' "$(http_code "$BASE/nope")" '404'
ok '実在しない .php は 404' "$(http_code "$BASE/nope.php")" '404'
ok 'ドットファイルは配信しない' "$(http_code "$BASE/.env")" '403'
ok 'プロファイラが無い' "$(http_code "$BASE/_profiler")" '404'

# ---------------------------------------------------------------------------
# 4. https の裏での「この港を保存」
#    trusted_proxies が無いと、Origin（https）とリクエスト（http）のスキームが合わず、
#    stateless CSRF が不正扱いになって Cookie が保存されない
# ---------------------------------------------------------------------------

section '4. リバースプロキシ（https）の裏での保存'

PROXY_HEADERS=(-H "Host: ${HOST}" -H 'X-Forwarded-Proto: https' -H "X-Forwarded-Host: ${HOST}" -H 'X-Forwarded-Port: 443')

PORTS_HTML="$(curl -s "${PROXY_HEADERS[@]}" "$BASE/ports")"
TOKEN="$(printf '%s' "$PORTS_HTML" | grep -oE 'name="_token" value="[^"]*"' | head -1 | sed -E 's/.*value="([^"]*)"/\1/' || true)"
PORT_ID="$(printf '%s' "$PORTS_HTML" | grep -oE '<option value="[0-9]+"' | head -1 | grep -oE '[0-9]+' || true)"

ok 'CSRF トークンと港が取れた' \
   "$([ -n "$TOKEN" ] && [ -n "$PORT_ID" ] && echo あり || echo なし)" 'あり'

# save_headers <追加の curl 引数...>  https のページから「この港を保存」したときの POST。
# Sec-Fetch-Site は付けない。付いていると Symfony はそれだけで判定し、Origin とスキームを比べない。
# 付けないブラウザ（古い Safari など）では Origin で判定されるので、そちらの経路を通す
save_headers() {
    curl -s -o /dev/null -D - "$@" \
        -H "Host: ${HOST}" -H "Origin: https://${HOST}" \
        --data-urlencode "_token=${TOKEN}" --data-urlencode "port=${PORT_ID}" \
        --data-urlencode 'dir=' --data-urlencode 'action=save' \
        "$BASE/ports/filter"
}

SAVED="$(save_headers -H 'X-Forwarded-Proto: https' -H "X-Forwarded-Host: ${HOST}" -H 'X-Forwarded-Port: 443')"
contains '保存すると 303 で戻る' "$SAVED" ' 303'
contains '保存の Cookie が発行される' "$SAVED" 'port_filter='

# 対照実験。X-Forwarded-Proto が無ければ http と見なされ、保存されないこと。
# これが通らないなら、上の確認は trusted_proxies の有無を見分けられていない
NOT_SAVED="$(save_headers)"
ok 'https と分からなければ保存しない' \
   "$(printf '%s' "$NOT_SAVED" | grep -ci '^set-cookie: port_filter=' | tr -d ' ' || true)" '0'

# ---------------------------------------------------------------------------
# 5. 再デプロイをまたいだ永続化
# ---------------------------------------------------------------------------

section '5. 再デプロイ後のデータ保持'

mysql_one "insert into scraper_logs (ferry_company_id, started_at, status, records_created, records_updated, error_message, created_at, updated_at)
           values (1, now(), 'success', 0, 0, 'verify-persist', now(), now())" >/dev/null
readonly PERSIST_SQL="select count(*) from scraper_logs where error_message = 'verify-persist'"

# -v は付けない。本番の再デプロイと同じ操作にする
compose down >/dev/null 2>&1
compose up -d mysql app >/dev/null 2>&1
wait_healthy app || abort_unhealthy

ok 'DB の行が残っている' "$(mysql_one "$PERSIST_SQL")" '1'

# ---------------------------------------------------------------------------
# 6. ホストの nginx の vhost
# ---------------------------------------------------------------------------

section '6. ホストの nginx の vhost'

# 読み取り専用でマウントした先は書き換えられないので、置き換えながら別の場所に書き出す
VHOST_CHECK="$(docker run --rm -v "$PWD/deploy/nginx/shipinfo-v2.conf:/tmp/vhost.conf:ro" \
    "$NGINX_IMAGE" sh -c \
    "sed 's/DOMAIN/${HOST}/' /tmp/vhost.conf > /etc/nginx/conf.d/default.conf && nginx -t" 2>&1 || true)"

contains '構文が正しい' "$VHOST_CHECK" 'syntax is ok'

# vhost を本当に通して、検索エンジンに載せないヘッダーが付くか確かめる。
# proxy_pass の先（ホストの 127.0.0.1:8002）を compose のネットワーク上の app に差し替えて動かす
docker rm -f "$VHOST_CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$VHOST_CONTAINER" --network "${PROJECT}_default" -p "127.0.0.1:${VHOST_PORT}:80" \
    -v "$PWD/deploy/nginx/shipinfo-v2.conf:/tmp/vhost.conf:ro" \
    "$NGINX_IMAGE" sh -c \
    "sed -e 's/DOMAIN/${HOST}/' -e 's#http://127.0.0.1:[0-9]*#http://app:80#' /tmp/vhost.conf > /etc/nginx/conf.d/default.conf && exec nginx -g 'daemon off;'" >/dev/null
for _ in $(seq 1 20); do
    [ "$(http_code -H "Host: ${HOST}" "http://127.0.0.1:${VHOST_PORT}/")" = '200' ] && break
    sleep 1
done

VIA_VHOST="$(curl -s -o /dev/null -D - -H "Host: ${HOST}" "http://127.0.0.1:${VHOST_PORT}/")"
contains 'vhost 経由でトップが返る' "$VIA_VHOST" ' 200'
contains '検索エンジンに載せない (X-Robots-Tag)' "$VIA_VHOST" 'X-Robots-Tag: noindex, nofollow'
# エラーページにも付くこと（always が無いと 2xx/3xx 以外では付かない）
contains '404 にも付く' \
    "$(curl -s -o /dev/null -D - -H "Host: ${HOST}" "http://127.0.0.1:${VHOST_PORT}/nope")" 'X-Robots-Tag: noindex, nofollow'

# ---------------------------------------------------------------------------

section '結果'
printf '  成功 %d / 失敗 %d\n' "$PASSED" "$FAILED"

if [ "$FAILED" -gt 0 ]; then
    printf '\n%s本番等価スモークテストに失敗した。このままマージするとデプロイが壊れる。%s\n' "$C_NG" "$C_OFF"
    exit 1
fi

printf '\n%s本番構成で動くことを確かめた。%s\n' "$C_OK" "$C_OFF"
