#!/bin/sh
# マイグレーションとキャッシュの生成を済ませてから supervisord に処理を渡す。
#
# bin/console はすべて www-data で動かす。root で動かすと var/ に root 所有の
# キャッシュが残り、php-fpm（www-data）が書き換えられなくなる。
set -e

console() {
    su -s /bin/sh www-data -c "php bin/console $*"
}

# compose.prod.yml で mysql の healthy を待っているが、初回は init スクリプト
# （01_schema.sql・02_seed.sql）の直後で接続が不安定なことがあるので、念のため待つ
echo "[entrypoint] MySQL に接続できるか確かめています..."
i=0
until console dbal:run-sql --quiet "'SELECT 1'" >/dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge 30 ]; then
        echo "[entrypoint] MySQL に接続できませんでした。中止します。" >&2
        exit 1
    fi
    sleep 2
done

# 最初のマイグレーションは 01_schema.sql のテーブルを ALTER する。
# 01_schema.sql は MySQL の初回起動時に docker-entrypoint-initdb.d から流れている
echo "[entrypoint] マイグレーションを実行します"
console doctrine:migrations:migrate --no-interaction --allow-no-migration

echo "[entrypoint] キャッシュを作ります"
console cache:warmup

echo "[entrypoint] 起動します"
exec "$@"
