# McGill Course Explorer

Scrape, resolve, embed, and query McGill University's ~4,900 courses across 12 faculties. Full pipeline: Playwright scraper, Jaro-Winkler entity resolution, Voyage AI embeddings, LangGraph orchestration, FastAPI + SSE API, React + D3 frontend.

## Quick Start

```bash
cp .env.example .env          # fill in API keys
make db                       # start Postgres + Neo4j
make seed                     # load courses from data/courses.json
make serve                    # API on :8001
make frontend                 # UI on :5174
```

## Features

- **Browse by faculty/department** — landing page shows all 12 faculties, click into one to see its departments, then drill into individual courses
- **Per-department scraping** — scrape button on each department triggers the pipeline for just that department's courses (writes to JSON + database)
- **Prerequisite chain visualizer** — D3 force-directed graph on each course page showing the full prerequisite/corequisite DAG with depth-based styling, hover tooltips, and click-to-navigate
- **Agentic chat** — ask natural language questions about courses, answered via hybrid retrieval (keyword + semantic + graph) and Claude synthesis over SSE
- **Full ingest pipeline** — scrape, resolve, embed in one shot with real-time SSE progress streaming

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
make start            Stop everything, then start db + API + frontend
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

### API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/faculties` | List all faculties with course counts |
| `GET /api/v1/faculties/{slug}/departments` | List departments for a faculty |
| `GET /api/v1/departments/{code}/courses` | List courses in a department |
| `GET /api/v1/courses/{code}` | Full course detail with resolved prerequisites |
| `GET /api/v1/graph/tree/{code}` | Prerequisite DAG (flat nodes + edges with depth) |
| `GET /api/v1/search` | Hybrid search (keyword/semantic/hybrid modes) |
| `POST /api/v1/pipeline/run` | Trigger pipeline (supports `faculty_filter` and `dept_filter`) |
| `GET /api/v1/pipeline/stream/{run_id}` | SSE stream for pipeline progress |
| `POST /api/v1/chat/session` | Create chat session |
| `GET /api/v1/chat/stream` | SSE stream for chat responses |

## Stack

- **Backend**: Python 3.12, FastAPI, LangGraph, asyncpg, neo4j, rapidfuzz, Voyage AI, Anthropic
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS 4, Zustand, react-router-dom, D3
- **Databases**: PostgreSQL 17 + pgvector, Neo4j 5
- **Infra**: uv, Docker Compose, nginx
