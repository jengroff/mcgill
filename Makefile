.PHONY: help start install dev up down rebuild logs serve db db-down frontend frontend-build seed scrape pipeline test test-cov lint format typecheck clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

start: ## Stop everything, then start db + API + frontend
	@docker-compose down 2>/dev/null || true
	@lsof -ti:8001,5174 2>/dev/null | xargs -r kill 2>/dev/null || true
	@echo "Starting databases..."
	@docker-compose up -d --wait postgres neo4j
	@sleep 3
	@echo "Starting API on :8001..."
	@uv run uvicorn mcgill.api.app:create_app --factory --reload --host 0.0.0.0 --port 8001 &
	@echo "Starting frontend on :5174..."
	@cd frontend && npm run dev &
	@echo ""
	@echo "  API:      http://localhost:8001"
	@echo "  Docs:     http://localhost:8001/docs"
	@echo "  Frontend: http://localhost:5174"
	@echo "  Neo4j:    http://localhost:7475"
	@echo "  Postgres: localhost:5433"
	@echo ""
	@wait

install: ## Install package
	uv pip install -e .

dev: ## Install with dev deps
	uv pip install -e ".[dev]"

up: ## Start all services via Docker
	docker-compose up -d --wait
	@echo ""
	@echo "  API:      http://localhost:8001"
	@echo "  Docs:     http://localhost:8001/docs"
	@echo "  Neo4j:    http://localhost:7475"
	@echo "  Postgres: localhost:5433"

down: ## Stop all Docker services
	docker-compose down

rebuild: ## Rebuild containers from scratch (no cache)
	docker-compose down -v
	docker-compose build --no-cache
	docker-compose up -d --wait

logs: ## Tail Docker logs
	docker-compose logs -f

db: ## Start databases only (Neo4j + Postgres)
	docker-compose up -d --wait postgres neo4j

db-down: ## Stop databases
	docker-compose down postgres neo4j

serve: ## Start API locally via uv (databases must be running)
	uv run uvicorn mcgill.api.app:create_app --factory --reload --host 0.0.0.0 --port 8001

frontend: ## Start frontend dev server
	cd frontend && npm run dev

frontend-build: ## Production build of frontend
	cd frontend && npm run build

seed: ## Load courses.json into databases
	uv run mcgill seed

scrape: ## Run scraper (usage: make scrape FACULTY="Science")
	uv run mcgill scrape $(if $(FACULTY),--faculty "$(FACULTY)",)

pipeline: ## Run full ingest pipeline (scrape → resolve → embed)
	uv run mcgill pipeline

test: ## Run test suite
	uv run pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage
	uv run pytest tests/ -v --tb=short --cov=mcgill --cov-report=term-missing

lint: ## Check linting
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

format: ## Auto-fix lint + format
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

typecheck: ## Run mypy
	uv run mypy src/mcgill/

clean: ## Remove build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist build .mypy_cache .ruff_cache .pytest_cache htmlcov
