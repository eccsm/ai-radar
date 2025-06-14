# AI Radar Makefile
# Cross-platform task runner for Docker Compose and Kubernetes operations

.PHONY: help up down dev prod logs build clean vault-ui ui api status reset-db backup test

# Default target
help: ## Show this help message
	@echo "AI Radar Management Commands:"
	@echo "=============================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Environment detection
SHELL := /bin/bash
OS := $(shell uname -s)
ifeq ($(OS),Windows_NT)
    DETECTED_OS := Windows
    COMPOSE_CMD := docker-compose
else
    DETECTED_OS := $(OS)
    COMPOSE_CMD := docker compose
endif

# Service management
up: vault-check ## Start all services in development mode
	$(COMPOSE_CMD) --profile dev up -d

down: ## Stop all services
	$(COMPOSE_CMD) down

prod: vault-check ## Start all services in production mode
	$(COMPOSE_CMD) --profile prod up -d

dev: vault-check ## Start all services in development mode with code mounting
	$(COMPOSE_CMD) --profile dev up -d

restart: ## Restart all services
	$(COMPOSE_CMD) restart

# Vault management
vault-check: ## Check if Vault is running, start if needed
	@echo "Checking Vault status..."
	@if ! $(COMPOSE_CMD) ps vault | grep -q "Up"; then \
		echo "Starting Vault..."; \
		$(COMPOSE_CMD) up -d vault; \
		sleep 5; \
		$(MAKE) vault-init; \
	else \
		echo "Vault is already running"; \
	fi

vault-init: ## Initialize Vault with secrets
	@echo "Initializing Vault..."
	$(COMPOSE_CMD) exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault secrets enable -path=ai-radar kv-v2 || true"
	$(COMPOSE_CMD) exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault kv put ai-radar/database host=db port=5432 username=ai password=ai_pwd database=ai_radar"
	$(COMPOSE_CMD) exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault kv put ai-radar/nats host=nats port=4222 subject_prefix=ai-radar stream_name=ai-radar"
	$(COMPOSE_CMD) exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault kv put ai-radar/minio endpoint=minio:9000 access_key=minio secret_key=minio_pwd bucket=ai-radar-content"
	$(COMPOSE_CMD) exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault kv put ai-radar/api-keys newsapi=your_newsapi_key_here openai=your_openai_key_here slack=your_slack_webhook_here"

vault-ui: ## Open Vault UI in browser
ifeq ($(DETECTED_OS),Windows)
	start http://localhost:8200
else ifeq ($(DETECTED_OS),Darwin)
	open http://localhost:8200
else
	xdg-open http://localhost:8200 2>/dev/null || echo "Open http://localhost:8200 in your browser"
endif

# Application URLs
ui: ## Open React UI in browser
ifeq ($(DETECTED_OS),Windows)
	start http://localhost:3000
else ifeq ($(DETECTED_OS),Darwin)
	open http://localhost:3000
else
	xdg-open http://localhost:3000 2>/dev/null || echo "Open http://localhost:3000 in your browser"
endif

api: ## Open API Swagger UI in browser
ifeq ($(DETECTED_OS),Windows)
	start http://localhost:8000/docs
else ifeq ($(DETECTED_OS),Darwin)
	open http://localhost:8000/docs
else
	xdg-open http://localhost:8000/docs 2>/dev/null || echo "Open http://localhost:8000/docs in your browser"
endif

# Logging and monitoring
logs: ## Show logs for all services (use AGENT=service_name for specific service)
ifdef AGENT
	$(COMPOSE_CMD) logs -f $(AGENT)
else
	$(COMPOSE_CMD) logs -f
endif

status: ## Show status of all services
	@echo "Service Status:"
	@echo "==============="
	$(COMPOSE_CMD) ps

health: ## Check health of all services
	@echo "Health Check:"
	@echo "============="
	@curl -f http://localhost:8000/healthz >/dev/null 2>&1 && echo "✅ API: Healthy" || echo "❌ API: Unhealthy"
	@curl -f http://localhost:3000 >/dev/null 2>&1 && echo "✅ UI: Healthy" || echo "❌ UI: Unhealthy"
	@curl -f http://localhost:8200/v1/sys/health >/dev/null 2>&1 && echo "✅ Vault: Healthy" || echo "❌ Vault: Unhealthy"
	@curl -f http://localhost:9000/minio/health/live >/dev/null 2>&1 && echo "✅ MinIO: Healthy" || echo "❌ MinIO: Unhealthy"

metrics: ## Show Prometheus metrics endpoint
	@echo "Prometheus metrics available at: http://localhost:9090"
	@echo "Grafana dashboard available at: http://localhost:33000"

# Database operations
reset-db: ## Reset the database (delete all articles)
	$(COMPOSE_CMD) exec db psql -U ai -d ai_radar -c "TRUNCATE TABLE ai_radar.articles CASCADE;"
	@echo "Database reset completed"

db-shell: ## Open database shell
	$(COMPOSE_CMD) exec db psql -U ai -d ai_radar

backup: ## Run manual database backup
	$(COMPOSE_CMD) exec backup /bin/bash -c "pg_dump -h db -U ai ai_radar > /backups/$$(date +%F).sql"
	$(COMPOSE_CMD) exec backup /bin/bash -c "mc config host add minio http://minio:9000 minio minio_pwd"
	$(COMPOSE_CMD) exec backup /bin/bash -c "mc cp /backups/$$(date +%F).sql minio/ai-radar-backups/"
	@echo "Backup completed"

# Build and deployment
build: ## Rebuild all services
ifdef SERVICE
	$(COMPOSE_CMD) build --no-cache $(SERVICE)
	$(COMPOSE_CMD) up -d $(SERVICE)
else
	$(COMPOSE_CMD) build --no-cache
	$(COMPOSE_CMD) up -d
endif

rebuild: ## Rebuild and restart specific service (use SERVICE=service_name)
ifdef SERVICE
	$(COMPOSE_CMD) build --no-cache $(SERVICE)
	$(COMPOSE_CMD) up -d $(SERVICE)
	@echo "Service $(SERVICE) rebuilt and restarted"
else
	@echo "Usage: make rebuild SERVICE=service_name"
	@echo "Available services: fetcher-agent, summariser-agent, ranker-agent, scheduler-agent, api, ui"
endif

# Testing
test: ## Run integration tests
	@echo "Setting up test environment..."
	mkdir -p secrets
	echo "ai_pwd" > secrets/pg_pass.txt
	echo "minio" > secrets/minio_user.txt  
	echo "minio_pwd" > secrets/minio_pass.txt
	echo "postgresql://ai:ai_pwd@localhost:5432/ai_radar" > secrets/postgres_url.txt
	echo "nats://localhost:4222" > secrets/nats_url.txt
	$(COMPOSE_CMD) --profile dev up -d
	@echo "Waiting for services to be ready..."
	sleep 30
	python -m pytest tests/integration/ -v
	$(COMPOSE_CMD) down

test-unit: ## Run unit tests for all agents
	@echo "Running unit tests..."
	cd agents && python -m pytest tests/ -v

# Cleanup operations
clean: ## Remove all containers and volumes
	$(COMPOSE_CMD) down -v --remove-orphans
	docker system prune -f

prune: ## Remove unused Docker resources
	docker system prune -f
	docker volume prune -f
	docker network prune -f

reset: clean setup ## Full reset: clean everything and setup fresh

# Setup operations  
setup: ## Create required secret files and directories
	@echo "Setting up AI Radar..."
	mkdir -p secrets monitoring/loki monitoring/promtail backups hcl/templates vault-auth
	@echo "Creating secret files..."
	echo "ai_pwd" > secrets/pg_pass.txt
	echo "minio" > secrets/minio_user.txt
	echo "minio_pwd" > secrets/minio_pass.txt
	echo "postgresql://ai:ai_pwd@db:5432/ai_radar" > secrets/postgres_url.txt
	echo "nats://nats:4222" > secrets/nats_url.txt
	echo "minio:9000" > secrets/minio_endpoint.txt
	echo "your_newsapi_key_here" > secrets/newsapi_key.txt
	echo "your_openai_key_here" > secrets/openai_key.txt
	echo "admin" > secrets/grafana_user.txt
	echo "admin" > secrets/grafana_pass.txt
	echo "admin@example.com" > secrets/pgadmin_email.txt
	echo "admin" > secrets/pgadmin_pass.txt
	echo "postgresql://ai:ai_pwd@db:5432/ai_radar?sslmode=disable" > secrets/postgres_exporter_dsn.txt
	echo "root" > secrets/vault_token.txt
	@echo "✅ Setup completed! Run 'make dev' to start services"

# Data operations
add-sources: ## Add sample RSS sources to database
	python add_sources.py

trigger-fetch: ## Trigger RSS feed fetch manually  
	python trigger_feed_local.py

# Kubernetes operations (requires kompose)
k8s-convert: ## Convert Docker Compose to Kubernetes manifests
	@if command -v kompose >/dev/null 2>&1; then \
		mkdir -p k8s-preview; \
		kompose convert -f docker-compose.yaml --profile prod -o k8s-preview/; \
		echo "✅ Kubernetes manifests generated in k8s-preview/"; \
	else \
		echo "❌ kompose not found. Install it first:"; \
		echo "  brew install kompose  # macOS"; \
		echo "  choco install kompose # Windows"; \
	fi

k8s-deploy: k8s-convert ## Deploy to Kubernetes (requires kubectl and cluster access)
	kubectl create namespace ai-radar --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -f k8s-preview/

# Development helpers
dev-logs: ## Show logs for development services only
	$(COMPOSE_CMD) logs -f fetcher-agent-dev summariser-agent-dev ranker-agent-dev scheduler-agent-dev

shell-fetcher: ## Open shell in fetcher agent container
	$(COMPOSE_CMD) exec fetcher-agent-dev /bin/bash

shell-summariser: ## Open shell in summariser agent container  
	$(COMPOSE_CMD) exec summariser-agent-dev /bin/bash

# Environment info
info: ## Show environment information
	@echo "AI Radar Environment Information"
	@echo "================================"
	@echo "OS: $(DETECTED_OS)"
	@echo "Docker Compose Command: $(COMPOSE_CMD)"
	@echo "Docker Version: $$(docker --version)"
	@echo "Docker Compose Version: $$($(COMPOSE_CMD) --version)"
	@echo ""
	@echo "Available Profiles:"
	@echo "  dev  - Development mode with hot reload"
	@echo "  prod - Production mode with optimized images" 
	@echo ""
	@echo "Key URLs:"
	@echo "  UI:         http://localhost:3000"
	@echo "  API:        http://localhost:8000"
	@echo "  Vault UI:   http://localhost:8200"
	@echo "  MinIO UI:   http://localhost:9001"
	@echo "  Grafana:    http://localhost:33000"
	@echo "  Prometheus: http://localhost:9090"