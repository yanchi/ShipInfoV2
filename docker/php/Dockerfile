FROM php:8.3-fpm-alpine

# System dependencies
RUN apk add --no-cache \
    git \
    curl \
    unzip \
    icu-dev \
    libzip-dev \
    oniguruma-dev

# PHP extensions
RUN docker-php-ext-install \
    pdo_mysql \
    intl \
    zip \
    opcache \
    mbstring

# Xdebug for local dev
RUN pecl install xdebug && docker-php-ext-enable xdebug

# Composer
COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

WORKDIR /var/www/html

EXPOSE 9000
CMD ["php-fpm"]
