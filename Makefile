.PHONY: help up up-tools down build logs logs-php logs-scraper \
        shell-php shell-scraper \
        migrate migrate-diff fixtures cache-clear \
        test-php test-scraper lint-scraper \
        init

DOCKER_COMPOSE = docker compose
PHP_SERVICE    = php
SCRAPER_SERVICE = scraper

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
	@echo ""
	@echo "Setup complete!"
	@echo "  API:        http://localhost:8080/api"
	@echo "  phpMyAdmin: make up-tools && open http://localhost:8081"
