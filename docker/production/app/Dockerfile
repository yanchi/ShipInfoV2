# 本番用の Web アプリ（Symfony）イメージ。ビルドコンテキストはリポジトリのルート。
#
# 開発用の docker/php/Dockerfile とは別物。開発用はソースをバインドマウントし、
# nginx も別コンテナで動かす。こちらはコードと依存を焼き込み、nginx と php-fpm を
# 1 コンテナで動かす自己完結イメージ（compose.prod.yml から起動する）。
#
# VPS ではホストの nginx が 80/443 と TLS を持っているので、このコンテナは
# 127.0.0.1 の空きポートで待ち受け、ホストの nginx からリバースプロキシされる。

# ---------- 1. PHP の依存を解決 ----------
FROM php:8.3-cli-alpine AS vendor

RUN apk add --no-cache git unzip

# composer はイメージからバイナリだけ取る（Docker がダイジェストを検証する）
COPY --from=composer:2 /usr/bin/composer /usr/local/bin/composer

WORKDIR /app
COPY app/composer.json app/composer.lock ./
# スクリプトは無効にする。この時点ではアプリ本体が無く bin/console を動かせないため
RUN composer install \
        --no-dev \
        --no-scripts \
        --no-autoloader \
        --prefer-dist \
        --no-interaction

COPY app/ .
RUN composer dump-autoload --optimize --no-dev --classmap-authoritative

# ---------- 2. 実行イメージ ----------
FROM php:8.3-fpm-alpine AS runtime

RUN apk add --no-cache nginx supervisor icu-libs \
    && apk add --no-cache --virtual .build-deps $PHPIZE_DEPS icu-dev \
    && docker-php-ext-install -j"$(nproc)" pdo_mysql intl opcache \
    && apk del .build-deps

# 時刻は日本時間（CLAUDE.md の「重要な設計決定」）。
# opcache.validate_timestamps = 0 にできるのは、コードをイメージに焼き込んでいて実行中に変わらないから
RUN { \
        echo 'date.timezone = Asia/Tokyo'; \
        echo 'memory_limit = 256M'; \
        echo 'expose_php = Off'; \
        echo 'opcache.enable = 1'; \
        echo 'opcache.memory_consumption = 128'; \
        echo 'opcache.max_accelerated_files = 20000'; \
        echo 'opcache.validate_timestamps = 0'; \
    } > /usr/local/etc/php/conf.d/99-app.ini

# php-fpm は既定で環境変数を捨てる（clear_env = yes）。
# APP_SECRET・DATABASE_URL などは compose の environment で渡すので、そのまま通す
RUN echo 'clear_env = no' >> /usr/local/etc/php-fpm.d/www.conf

ENV APP_ENV=prod \
    APP_DEBUG=0 \
    APP_SHARE_DIR=var/share

WORKDIR /var/www/html

COPY --from=vendor --chown=www-data:www-data /app /var/www/html

# .env は git 管理外だが bootEnv が読むので空で作る（値はすべて環境変数で渡す）
RUN touch .env \
    && mkdir -p var \
    && chown -R www-data:www-data .env var

# nginx のワーカーを www-data で動かすので、一時ディレクトリの所有者を合わせる。
# Alpine の nginx パッケージは nginx ユーザー所有で作るため、そのままだと
# リクエストボディがバッファを超えたときに書けず 500 になる
RUN chown -R www-data:www-data /var/lib/nginx /var/log/nginx

COPY docker/production/app/nginx.conf       /etc/nginx/nginx.conf
COPY docker/production/app/supervisord.conf /etc/supervisord.conf
COPY docker/production/app/entrypoint.sh    /usr/local/bin/entrypoint
RUN chmod +x /usr/local/bin/entrypoint

EXPOSE 80

# トップページは DB を読むので、nginx・php-fpm・MySQL までまとめて確かめられる
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD wget -qO /dev/null http://127.0.0.1/ || exit 1

ENTRYPOINT ["entrypoint"]
CMD ["supervisord", "-c", "/etc/supervisord.conf"]
