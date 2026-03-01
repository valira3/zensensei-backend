.PHONY: help install lint format test test-cov build up down logs clean neo4j-shell redis-cli db-seed proto-gen deploy-dev

SERVICES := user_service graph_query_service ai_reasoning_service integration_service notification_service analytics_service api_gateway

help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/## //' | column -t -s ':'

install:
	@echo "Installing shared dependencies"
	pip install -r services/shared/requirements.txt
	@for svc in $(SERVICES); do \
		if [ -f services/$$svc/requirements.txt ]; then \
			pip install -r services/$$svc/requirements.txt; \
		fi; \
	done

lint:
	ruff check services/
	black --check services/
	isort --check-only services/

format:
	black services/
	isort services/
	ruff check --fix services/

test:
	@for svc in $(SERVICES); do \
		if [ -d services/$$svc/tests ]; then \
			python -m pytest services/$$svc/tests/ -v --tb=short; \
		fi; \
	done

build:
	@for svc in $(SERVICES); do \
		docker build -t zensensei/$$svc:dev services/$$svc/; \
	done

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f $(svc)

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete
