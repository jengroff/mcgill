.PHONY: help start install dev up down rebuild rebuild-keep logs serve db db-down frontend frontend-build rust-build rust-test bench seed pipeline pipeline-general test test-cov lint format typecheck clean deploy-setup

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

start: ## Stop everything, then start db + API + frontend
	@docker compose down 2>/dev/null || true
	@lsof -ti:8001,5174 2>/dev/null | xargs -r kill 2>/dev/null || true
	@echo "Starting databases..."
	@docker compose up -d --wait postgres neo4j
	@sleep 3
	@echo "Starting API on :8001..."
	@uv run uvicorn backend.api.app:create_app --factory --reload --host 0.0.0.0 --port 8001 &
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
	docker compose up -d --wait
	@echo ""
	@echo "  API:      http://localhost:8001"
	@echo "  Docs:     http://localhost:8001/docs"
	@echo "  Neo4j:    http://localhost:7475"
	@echo "  Postgres: localhost:5433"

down: ## Stop all Docker services
	docker compose down

rebuild: ## Rebuild containers from scratch, preserves volumes (Postgres, Neo4j)
	docker compose down
	docker compose build --no-cache
	docker compose up -d --wait

app: # Rebuild app container only
	docker compose up -d --build app

rebuild-keep: ## Rebuild containers but keep database volumes
	docker compose down
	docker compose build --no-cache
	docker compose up -d --wait

logs: ## Tail Docker logs
	docker compose logs -f

db: ## Start databases only (Neo4j + Postgres)
	docker compose up -d --wait postgres neo4j

db-down: ## Stop databases
	docker compose down postgres neo4j

serve: ## Start API locally via uv (databases must be running)
	uv run uvicorn backend.api.app:create_app --factory --reload --host 0.0.0.0 --port 8001

frontend: ## Start frontend dev server
	cd frontend && npm run dev

frontend-build: ## Production build of frontend
	cd frontend && npm run build

rust-build: ## Build Rust extension (release)
	uv run maturin develop --release

rust-test: ## Run Rust unit tests
	cargo test

bench: rust-build ## Run benchmark suite (Rust vs Python jaro_winkler)
	uv run python benchmark.py

seed: # (hidden) Load courses.json into databases
	uv run mcgill seed

pipeline: ## Run full ingest pipeline (usage: make pipeline FACULTY="Science" DEPT="COMP" FORCE=1)
	uv run mcgill pipeline $(if $(FACULTY),--faculty "$(FACULTY)",) $(if $(DEPT),--dept "$(DEPT)",) $(if $(FORCE),--force,)

pipeline-general: ## Ingest university-wide data: important dates, academic calendar, enrollment, exams, fees
	uv run mcgill pipeline --general

test: ## Run test suite
	uv run pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage
	uv run pytest tests/ -v --tb=short --cov=backend --cov-report=term-missing

lint: ## Check linting
	uv run ruff check backend/ tests/
	uv run ruff format --check backend/ tests/

format: ## Auto-fix lint + format
	uv run ruff check --fix backend/ tests/
	uv run ruff format backend/ tests/

typecheck: ## Run mypy
	uv run mypy backend/

clean: ## Remove build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist build .mypy_cache .ruff_cache .pytest_cache htmlcov

deploy-setup: ## Show required GitHub secrets for CI/CD
	@echo "Configure these GitHub repository secrets:"
	@echo "  EC2_HOST     — EC2 public IP or hostname"
	@echo "  EC2_USER     — SSH user (ubuntu or ec2-user)"
	@echo "  EC2_SSH_KEY  — Private SSH key for EC2"
	@echo ""
	@echo "Then push to main to trigger deployment."
