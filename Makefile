# ─── ZenSensei Backend Makefile ──────────────────────────────────────────────
# Run `make help` for a description of all available targets.

.PHONY: help setup dev stop clean test test-unit test-integration lint format \
        typecheck build seed deploy-staging deploy-prod logs shell status

# ─── Configuration ────────────────────────────────────────────────────────────

PYTHON      := python3.11
VENV        := .venv
PIP         := $(VENV)/bin/pip
PYTHON_BIN  := $(VENV)/bin/python
PYTEST      := $(VENV)/bin/pytest
RUFF        := $(VENV)/bin/ruff
BLACK       := $(VENV)/bin/black
MYPY        := $(VENV)/bin/mypy

DOCKER_COMPOSE := docker compose
GCP_REGION     := us-central1

# Detect CI environment to suppress interactive prompts
ifdef CI
  COMPOSE_ARGS := --no-ansi
else
  COMPOSE_ARGS :=
endif

# ─── Colors ───────────────────────────────────────────────────────────────────

BOLD  := \033[1m
RESET := \033[0m
GREEN := \033[32m
CYAN  := \033[36m
YELLOW := \033[33m
RED   := \033[31m

# ─── Default target ───────────────────────────────────────────────────────────

.DEFAULT_GOAL := help

# ─── Help ─────────────────────────────────────────────────────────────────────

help: ## Show this help message
	@echo ""
	@echo "$(BOLD)ZenSensei Backend — Developer Commands$(RESET)"
	@echo ""
	@echo "$(CYAN)Setup & Development:$(RESET)"
	@grep -E '^(setup|dev|stop|clean|seed|shell|logs|status):' Makefile | \
		awk -F':.*##' '{printf "  $(BOLD)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(CYAN)Testing & Quality:$(RESET)"
	@grep -E '^(test|test-unit|test-integration|lint|format|typecheck):' Makefile | \
		awk -F':.*##' '{printf "  $(BOLD)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(CYAN)Building & Deployment:$(RESET)"
	@grep -E '^(build|deploy-staging|deploy-prod):' Makefile | \
		awk -F':.*##' '{printf "  $(BOLD)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ─── Setup ────────────────────────────────────────────────────────────────────

setup: ## Install all Python dependencies into a local virtual environment
	@echo "$(BOLD)$(CYAN)→ Setting up virtual environment…$(RESET)"
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	@$(PIP) install --upgrade pip
	@$(PIP) install -r requirements.txt -r requirements-dev.txt
	@echo ""
	@echo "$(GREEN)✓ Dependencies installed.$(RESET)"
	@echo "  Activate with: $(BOLD)source $(VENV)/bin/activate$(RESET)"
	@echo ""

# ─── Development ──────────────────────────────────────────────────────────────

dev: ## Start all services using Docker Compose (full stack)
	@echo "$(BOLD)$(CYAN)→ Starting ZenSensei full stack…$(RESET)"
	@$(DOCKER_COMPOSE) $(COMPOSE_ARGS) up --build -d
	@echo ""
	@echo "$(GREEN)✓ Stack is up!$(RESET)"
	@echo ""
	@echo "  $(BOLD)Services:$(RESET)"
	@echo "  API Gateway        → http://localhost:4000"
	@echo "  User Service       → http://localhost:8001  (docs: /docs)"
	@echo "  Graph Query        → http://localhost:8002  (docs: /docs)"
	@echo "  AI Reasoning       → http://localhost:8003  (docs: /docs)"
	@echo "  Integration        → http://localhost:8004  (docs: /docs)"
	@echo "  Notifications      → http://localhost:8005  (docs: /docs)"
	@echo "  Analytics          → http://localhost:8006  (docs: /docs)"
	@echo ""
	@echo "  $(BOLD)Infrastructure:$(RESET)"
	@echo "  Neo4j Browser      → http://localhost:7474"
	@echo "  Redis              → localhost:6379"
	@echo "  Firestore Emulator → http://localhost:8080"
	@echo ""
	@echo "  Run $(BOLD)make seed$(RESET) to load sample data."
	@echo ""

stop: ## Stop all running Docker Compose services
	@echo "$(BOLD)$(CYAN)→ Stopping services…$(RESET)"
	@$(DOCKER_COMPOSE) down
	@echo "$(GREEN)✓ All services stopped.$(RESET)"

status: ## Show the status of all Docker Compose services
	@$(DOCKER_COMPOSE) ps

logs: ## Follow logs for all services (SERVICE=name for a single service)
	@$(DOCKER_COMPOSE) logs -f $(SERVICE)

shell: ## Open a bash shell in a running service container (SERVICE=user-service)
	@$(DOCKER_COMPOSE) exec $(or $(SERVICE),api-gateway) bash

# ─── Data ─────────────────────────────────────────────────────────────────────

seed: ## Seed the Neo4j graph and Firestore with sample development data
	@echo "$(BOLD)$(CYAN)→ Seeding sample data…$(RESET)"
	@$(DOCKER_COMPOSE) exec graph-query-service \
		python -c "from services.graph_query_service.scripts.seed import seed; import asyncio; asyncio.run(seed())" \
		2>/dev/null || \
		$(PYTHON_BIN) -m services.graph_query_service.scripts.seed
	@echo "$(GREEN)✓ Sample data loaded.$(RESET)"
	@echo "  Demo login: demo@zensensei.app / Demo!Zensensei2026"

# ─── Testing ──────────────────────────────────────────────────────────────────

test: ## Run the full test suite with coverage report
	@echo "$(BOLD)$(CYAN)→ Running all tests…$(RESET)"
	@$(PYTEST) tests/ \
		--cov=services \
		--cov=shared \
		--cov=gateway \
		--cov-report=term-missing \
		--cov-report=html:htmlcov \
		--cov-fail-under=70 \
		-v \
		--tb=short
	@echo ""
	@echo "$(GREEN)✓ Tests complete. Coverage report: htmlcov/index.html$(RESET)"

test-unit: ## Run only unit tests (no database required, fast)
	@echo "$(BOLD)$(CYAN)→ Running unit tests…$(RESET)"
	@$(PYTEST) tests/ -m "unit" -v --tb=short

test-integration: ## Run integration tests (requires running infrastructure)
	@echo "$(BOLD)$(CYAN)→ Running integration tests…$(RESET)"
	@$(PYTEST) tests/ -m "integration" -v --tb=short

test-service: ## Run tests for a specific service (SERVICE=user_service)
	@echo "$(BOLD)$(CYAN)→ Running tests for $(SERVICE)…$(RESET)"
	@$(PYTEST) tests/services/$(SERVICE)/ -v --tb=short

# ─── Code Quality ─────────────────────────────────────────────────────────────

lint: ## Run all linters (ruff, black check, mypy)
	@echo "$(BOLD)$(CYAN)→ Running linters…$(RESET)"
	@$(RUFF) check .
	@$(BLACK) --check .
	@$(MYPY) shared/ services/ gateway/
	@echo "$(GREEN)✓ All linters passed.$(RESET)"

format: ## Auto-format all Python source files with ruff and black
	@echo "$(BOLD)$(CYAN)→ Formatting code…$(RESET)"
	@$(RUFF) check --fix .
	@$(BLACK) .
	@echo "$(GREEN)✓ Formatting complete.$(RESET)"

typecheck: ## Run mypy type checking only
	@echo "$(BOLD)$(CYAN)→ Type checking…$(RESET)"
	@$(MYPY) shared/ services/ gateway/
	@echo "$(GREEN)✓ Type check passed.$(RESET)"

# ─── Build ─────────────────────────────────────────────────────────────────────

build: ## Build all Docker images via Docker Compose
	@echo "$(BOLD)$(CYAN)→ Building Docker images…$(RESET)"
	@$(DOCKER_COMPOSE) build
	@echo "$(GREEN)✓ All images built.$(RESET)"

# ─── Deployment ──────────────────────────────────────────────────────────────

deploy-staging: ## Deploy all services to the Railway staging environment
	@echo "$(BOLD)$(CYAN)→ Deploying to staging…$(RESET)"
	@bash scripts/deploy-railway.sh staging

deploy-prod: ## Deploy all services to the Railway production environment
	@echo "$(BOLD)$(YELLOW)⚠ Deploying to PRODUCTION…$(RESET)"
	@bash scripts/deploy-railway.sh production

# ─── Cleanup ────────────────────────────────────────────────────────────────

clean: ## Remove virtual environment, Python caches, and test artifacts
	@echo "$(BOLD)$(CYAN)→ Cleaning up…$(RESET)"
	@rm -rf $(VENV) .pytest_cache htmlcov .coverage coverage.xml
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name '*.pyc' -delete 2>/dev/null || true
	@echo "$(GREEN)✓ Clean.$(RESET)"
