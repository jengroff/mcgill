# McGill Course Explorer

Scrape, resolve, embed, and query McGill University's ~4,900 courses across 12 faculties. Layered architecture with reusable LangGraph workflow orchestration, stateless domain services, and a thin API delegation layer.

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
- **Per-department scraping** — scrape button on each department triggers the pipeline for just that department's courses
- **Prerequisite chain visualizer** — D3 force-directed graph on each course page showing the full prerequisite/corequisite DAG
- **User accounts** — register/login with email + password, JWT-based auth, persistent conversation history across sessions
- **Agentic chat** — ask natural language questions about courses, answered via hybrid retrieval (keyword + semantic + graph) and Claude synthesis over SSE
- **Chat-driven pipeline** — type "scrape Science" or "run pipeline for COMP" in chat to trigger a full ingest pipeline with streamed progress
- **Full ingest pipeline** — scrape, resolve, embed in one shot with real-time SSE progress streaming
- **PDF ingestion** — upload PDFs to extract, chunk, embed, and store in pgvector
- **Curriculum recommendations** — provide interests and completed courses, get AI-assembled course plans
- **Multi-semester planner** — Claude Agent SDK builds a realistic 2–4 semester curriculum plan, with VLM processing for uploaded PDF course guides

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
make pipeline         Run full ingest pipeline (make pipeline FACULTY="Science" DEPT="COMP")
make up               Start all services via Docker
make down             Stop all Docker services
make rebuild          Rebuild containers from scratch (wipes volumes)
make rebuild-keep     Rebuild containers, keep database volumes
make logs             Tail Docker logs
make test             Run test suite
make lint             Check linting
make format           Auto-fix lint + format
make typecheck        Run mypy
make clean            Remove build artifacts
make deploy-setup     Show required GitHub secrets for CI/CD
```

## Architecture

```
backend/
├── lib/            Reusable orchestration framework (zero domain knowledge)
│   ├── orchestrator.py    WorkflowOrchestrator ABC
│   ├── registry.py        WorkflowRegistry singleton
│   ├── state.py           BaseWorkflowState TypedDict
│   ├── sse.py             Shared SSE helpers
│   └── streaming.py       StreamingResponse factory
│
├── workflows/      LangGraph workflow definitions
│   ├── ingest/            Scrape → Resolve → Chunk → Embed
│   ├── retrieval/         Keyword + Semantic + Program + Graph → RRF fusion
│   ├── ingestion/         PDF / URL → Extract → Chunk → Embed → Store
│   ├── synthesis/         Chat synthesis + Curriculum assembly
│   └── planner/           Multi-semester curriculum planner (Agent SDK + VLM)
│
├── services/       Stateless domain services (no workflow/lib imports)
│   ├── scraping/          Browser, parser, catalogue, faculties registry
│   ├── resolution/        Jaro-Winkler, entity graph, prerequisites
│   ├── embedding/         Chunker, Voyage AI, vector store, retrieval
│   ├── pdf/               PDF text extraction (pymupdf + pdfplumber)
│   ├── vlm/               Vision Language Model for PDF course guide processing
│   └── synthesis/         Curriculum assembler (interest mapping, requirements)
│
├── db/             PostgreSQL + pgvector, Neo4j
├── models/         Pydantic models
├── api/            FastAPI routes (thin delegation to orchestrators)
│   ├── auth.py            JWT + bcrypt auth helpers, FastAPI dependencies
│   └── routes/auth.py     Register, login, /me endpoints
├── config.py
└── main.py         CLI entry point
```

### Layer Discipline

- `lib/` has zero imports from `workflows/` or `services/`
- `services/` has zero imports from `workflows/` or `lib/`
- `workflows/` nodes do not import from `api/`
- `api/` routes delegate to orchestrators, no inline business logic

### Registered Workflows

| Workflow | Description |
|----------|-------------|
| `ingest` | Scrape → resolve → chunk → embed |
| `retrieval` | Keyword + semantic + program + graph → RRF fusion |
| `ingestion` | PDF / URL → extract → chunk → embed → store |
| `synthesis` | Context packing → Claude synthesis |
| `curriculum` | Interest mapping → requirements → retrieval → prereq filter → rank → assemble |
| `planner` | Multi-semester curriculum planning via Claude Agent SDK + VLM PDF processing |

### API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/faculties` | List all faculties with course counts |
| `GET /api/v1/faculties/{slug}/departments` | List departments for a faculty |
| `GET /api/v1/departments/{code}/courses` | List courses in a department |
| `GET /api/v1/courses/{code}` | Full course detail with resolved prerequisites |
| `GET /api/v1/graph/tree/{code}` | Prerequisite DAG (flat nodes + edges with depth) |
| `GET /api/v1/search` | Hybrid search (keyword/semantic/hybrid modes) |
| `POST /api/v1/pipeline/run` | Trigger ingest pipeline (supports `faculty_filter`, `dept_filter`) |
| `GET /api/v1/pipeline/stream/{run_id}` | SSE stream for pipeline progress |
| `POST /api/v1/ingest/pdf` | Upload and ingest a PDF file |
| `POST /api/v1/curriculum/recommend` | Generate curriculum recommendations |
| `POST /api/v1/planner/plan` | Multi-semester curriculum plan (accepts PDF upload) |
| `POST /api/v1/planner/stream` | SSE stream for planner progress |
| `POST /api/v1/auth/register` | Create a new user account |
| `POST /api/v1/auth/login` | Authenticate with email + password |
| `GET /api/v1/auth/me` | Get current user profile (protected) |
| `POST /api/v1/chat/session` | Create or resume a chat session |
| `POST /api/v1/chat/ask` | Submit a question (or pipeline trigger) |
| `GET /api/v1/chat/stream` | SSE stream for chat responses |
| `GET /api/v1/chat/conversations` | List user's conversations (protected) |
| `GET /api/v1/chat/conversations/{id}/messages` | Get conversation message history (protected) |

### CLI Commands

```bash
mcgill serve                          # Start FastAPI server
mcgill scrape --faculty Science       # Scrape one faculty
mcgill pipeline --dept COMP           # Full pipeline for a department
mcgill pipeline --faculty engineering # Full pipeline for a faculty
mcgill seed                           # Load courses.json into databases
mcgill ingest-pdf syllabus.pdf --faculty science  # Ingest a PDF
mcgill curriculum --interests "machine learning" "statistics" --program computer-science
```

## Stack

- **Backend**: Python 3.12, FastAPI, LangGraph, Claude Agent SDK, asyncpg, neo4j, rapidfuzz, Voyage AI, Anthropic
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS 4, Zustand, react-router-dom, D3
- **Databases**: PostgreSQL 17 + pgvector, Neo4j 5
- **Auth**: JWT (PyJWT), bcrypt
- **Infra**: uv, Docker Compose, GitHub Actions CI/CD → GHCR → EC2

## Deployment

Pushing to `main` triggers a GitHub Actions workflow that builds the Docker image, pushes it to GHCR, and deploys to EC2 via SSH.

**GitHub secrets required** (Settings → Secrets → Actions):

| Secret | Description |
|--------|-------------|
| `EC2_HOST` | EC2 public IP or hostname |
| `EC2_USER` | SSH user (`ubuntu` or `ec2-user`) |
| `EC2_SSH_KEY` | Private SSH key for the instance |

**EC2 setup** — Docker and docker compose must be installed. Place `docker-compose.prod.yml` and `.env` in `~/mcgill/`, then start databases once:

```bash
cd ~/mcgill
docker compose -f docker-compose.prod.yml up -d postgres neo4j
```

Subsequent pushes to `main` will only replace the `app` container — databases stay running with their volumes intact.
