# McGill Course Explorer

Scrape, resolve, embed, and query McGill University course data. Full pipeline: Playwright scraper, Jaro-Winkler entity resolution, Voyage AI embeddings, LangGraph orchestration, FastAPI + SSE API, React frontend.

## Quick Start

```bash
cp .env.example .env          # fill in API keys
make db                       # start Postgres + Neo4j
make seed                     # load 2,161 courses from data/courses.json
make serve                    # API on :8001
make frontend                 # UI on :5174
```

## Ports

Offset from defaults to avoid conflicts with other projects on this machine.

| Service        | Port  |
|----------------|-------|
| Frontend (Vite)| 5174  |
| API (FastAPI)  | 8001  |
| PostgreSQL     | 5433  |
| Neo4j Bolt     | 7688  |
| Neo4j Browser  | 7475  |

## Make Targets

```
make help             Show all targets
make db               Start databases only (Postgres + Neo4j)
make db-down          Stop databases
make seed             Load courses.json into databases
make serve            Start API locally (databases must be running)
make frontend         Start frontend dev server
make scrape           Run scraper (optional: make scrape FACULTY="Science")
make pipeline         Run full ingest pipeline (scrape -> resolve -> embed)
make up               Start all services via Docker
make down             Stop all Docker services
make rebuild          Rebuild containers from scratch
make logs             Tail Docker logs
make test             Run test suite
make lint             Check linting
make format           Auto-fix lint + format
make typecheck        Run mypy
make clean            Remove build artifacts
```

## Architecture

```
Phase 1: Ingest     — Playwright scraper -> JSON + PostgreSQL + Neo4j
Phase 2: Resolve    — Jaro-Winkler entity resolution + prerequisite graph
Phase 3: Index      — Voyage AI embeddings + pgvector + full-text search
Phase 4: Query      — LangGraph agentic loop -> Claude synthesis -> SSE
```

## Stack

- **Backend**: Python 3.12, FastAPI, LangGraph, asyncpg, neo4j, rapidfuzz, Voyage AI, Anthropic
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS 4, Zustand, react-router-dom
- **Databases**: PostgreSQL 17 + pgvector, Neo4j 5
- **Infra**: uv, Docker Compose, nginx
