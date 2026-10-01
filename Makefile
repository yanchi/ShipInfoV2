.PHONY: help up up-tools down build logs logs-php logs-scraper \
        shell-php shell-scraper \
        migrate migrate-diff fixtures cache-clear \
        test-php test-scraper lint-scraper \
        init init-test-db reset-test-db check-test-token

DOCKER_COMPOSE = docker compose
PHP_SERVICE    = php
SCRAPER_SERVICE = scraper
MYSQL_SERVICE  = mysql

# テスト用 DB は ${DB_NAME}_test<TEST_TOKEN>（app/config/packages/doctrine.yaml の dbname_suffix と揃える）
TEST_TOKEN ?=
export TEST_TOKEN

# Default target
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Docker lifecycle ───────────────────────────────────────────

up: ## Start all services (detached)
	$(DOCKER_COMPOSE) up -d

up-tools: ## Start all services including phpMyAdmin
	$(DOCKER_COMPOSE) --profile tools up -d

down: ## Stop and remove containers
	$(DOCKER_COMPOSE) down

build: ## Rebuild Docker images (no cache)
	$(DOCKER_COMPOSE) build --no-cache

logs: ## Tail logs for all services
	$(DOCKER_COMPOSE) logs -f

logs-php: ## Tail PHP service logs
	$(DOCKER_COMPOSE) logs -f $(PHP_SERVICE)

logs-scraper: ## Tail scraper service logs
	$(DOCKER_COMPOSE) logs -f $(SCRAPER_SERVICE)

# ─── Symfony / PHP ──────────────────────────────────────────────

shell-php: ## Open shell in PHP container
	$(DOCKER_COMPOSE) exec $(PHP_SERVICE) sh

composer-install: ## Run composer install inside PHP container
	$(DOCKER_COMPOSE) exec $(PHP_SERVICE) composer install

migrate: ## Run Doctrine migrations
	$(DOCKER_COMPOSE) exec $(PHP_SERVICE) bin/console doctrine:migrations:migrate --no-interaction

migrate-diff: ## Generate migration from entity changes
	$(DOCKER_COMPOSE) exec $(PHP_SERVICE) bin/console doctrine:migrations:diff

fixtures: ## Load dev data fixtures
	$(DOCKER_COMPOSE) exec $(PHP_SERVICE) bin/console doctrine:fixtures:load --no-interaction

cache-clear: ## Clear Symfony cache
	$(DOCKER_COMPOSE) exec $(PHP_SERVICE) bin/console cache:clear

test-php: ## Run PHPUnit tests
	$(DOCKER_COMPOSE) exec $(PHP_SERVICE) bin/phpunit

# 最初のマイグレーションは 01_schema.sql が作ったテーブルを ALTER するので、
# 空の DB に migrate するだけでは初期化できない。01_schema.sql を流してから migrate する。
# 02_seed.sql は入れない（テストは自分でデータを作る。港マスタはマイグレーションが入れる）。
# TEST_TOKEN は DB 名（SQL の識別子）とシェルの文字列にそのまま入るので、英数字と _ だけに限る
check-test-token:
	@case "$$TEST_TOKEN" in *[!A-Za-z0-9_]*) \
	  echo "TEST_TOKEN は英数字と _ だけにしてください" >&2; exit 1;; esac

init-test-db: check-test-token ## Create the PHPUnit test DB (idempotent)
	$(DOCKER_COMPOSE) exec -T $(MYSQL_SERVICE) sh -c '\
	  export MYSQL_PWD="$$MYSQL_ROOT_PASSWORD"; DB="$${MYSQL_DATABASE}_test$(TEST_TOKEN)"; \
	  mysql -uroot -e "CREATE DATABASE IF NOT EXISTS \`$$DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; \
	    GRANT ALL PRIVILEGES ON \`$$DB\`.* TO \`$$MYSQL_USER\`@\`%\`;" \
	  && mysql -uroot "$$DB" < /docker-entrypoint-initdb.d/01_schema.sql'
	$(DOCKER_COMPOSE) exec -T -e TEST_TOKEN=$(TEST_TOKEN) $(PHP_SERVICE) \
	  bin/console doctrine:migrations:migrate --env=test --no-interaction

reset-test-db: check-test-token ## Drop and recreate the PHPUnit test DB
	$(DOCKER_COMPOSE) exec -T $(MYSQL_SERVICE) sh -c '\
	  export MYSQL_PWD="$$MYSQL_ROOT_PASSWORD"; DB="$${MYSQL_DATABASE}_test$(TEST_TOKEN)"; \
	  mysql -uroot -e "DROP DATABASE IF EXISTS \`$$DB\`;"'
	$(MAKE) init-test-db

# ─── Python scraper ─────────────────────────────────────────────

shell-scraper: ## Open shell in scraper container
	$(DOCKER_COMPOSE) exec $(SCRAPER_SERVICE) bash

scraper-run: ## Run scraper once immediately
	$(DOCKER_COMPOSE) exec $(SCRAPER_SERVICE) python -m scraper.main --once

test-scraper: ## Run Python tests (pytest)
	$(DOCKER_COMPOSE) exec $(SCRAPER_SERVICE) python -m pytest tests/ -v

lint-scraper: ## Lint Python code with ruff
	$(DOCKER_COMPOSE) exec $(SCRAPER_SERVICE) ruff check scraper/ tests/

# ─── First-time setup ───────────────────────────────────────────

init: ## First-time project setup
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")
	@test -f scraper/.env || (cp scraper/.env.example scraper/.env && echo "Created scraper/.env")
	$(DOCKER_COMPOSE) build
	$(DOCKER_COMPOSE) up -d
	@echo "Waiting for MySQL to be healthy..."
	@sleep 15
	$(MAKE) composer-install
	$(MAKE) migrate
	$(MAKE) init-test-db
	@echo ""
	@echo "Setup complete!"
	@echo "  API:        http://localhost:8080/api"
	@echo "  phpMyAdmin: make up-tools && open http://localhost:8081"
