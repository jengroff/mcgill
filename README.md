# McGill Course Explorer

Ingest, resolve, embed, and query McGill University's ~4,900 courses across 12 faculties. A conversational AI layer over a real university catalogue — backed by hybrid retrieval (keyword + semantic + graph), a Rust-accelerated entity resolution pipeline, and multi-agent curriculum planning.

## Quick Start

```bash
cp .env.example .env          # fill in API keys
make db                       # start Postgres + Neo4j
make pipeline FACULTY="Science"  # scrape, resolve, embed (populates all tables)
make serve                    # API on :8001
make frontend                 # UI on :5174
```

`make seed` is available as a shortcut to load pre-scraped data from `data/courses.json`, but the pipeline is the primary path and populates everything including faculties, departments, and department website URLs.

## Features

- **Hybrid retrieval** — queries fan out in parallel across keyword search, Voyage AI semantic embeddings, Neo4j prerequisite graph traversal, and structured SQL, then fuse results with reciprocal rank fusion (RRF)
- **Prerequisite DAG visualization** — D3 force-directed graphs render the full prerequisite/corequisite dependency tree for any course, with depth-based layout
- **Rust-accelerated entity resolution** — Jaro-Winkler similarity compiled to a native PyO3 extension for fuzzy matching across 4,900+ course names; pure-Python fallback when the extension isn't compiled
- **End-to-end ingest pipeline** — ingest, resolve, chunk, and embed an entire faculty in one shot with real-time SSE progress streaming and per-department deduplication
- **Curriculum planner** — three-panel layout with plan list, semester grid, and advisor chat; selecting a faculty and program auto-populates semesters with required courses, correct credits, and Fall/Winter term assignments; courses display titles, credits, and link to detail pages; the right-panel advisor chat is plan-aware (knows your courses, schedule, and uploaded documents) and provides personalized guidance; "Explain Plan" triggers the Claude Agent SDK planner for deep rationale; plans are fully editable; upload transcripts and AP score reports as context
- **Department website directory** — 70+ department website URLs and student resources (student societies, library guides, advisor contacts) injected into synthesis context, so the advisor can reference official department pages, the Food Science Association, library subject guides, and named foundation year contacts
- **Foundation program awareness** — Foundation Year program pages are explicitly scraped for Ag & Env Sci, Science, Arts, and Arts & Science faculties; synthesis prompt understands non-CEGEP students need a Foundation Program, mentions AP/IB exemptions, and cites specific contact emails
- **Chat-driven operations** — natural language interface that routes between course Q&A, pipeline triggers ("ingest Science"), and curriculum planning, all over SSE
- **PDF ingestion** — upload arbitrary PDFs to extract, chunk, embed, and store in pgvector alongside catalogue data

### Chat Examples

The chat understands course questions, pipeline commands, and curriculum planning requests:

```
"What do I need to take before Organic Chemistry 2?"
"Which computer science courses are offered in the winter term?"
"Compare Intro to Machine Learning and Statistical Learning"
"What 300-level math courses have no prerequisites?"
"Are there any physics courses related to quantum computing?"
"I'm an incoming freshman in Food Science — what do I need to take?"
"Ingest Science"                       → triggers ingest pipeline for the faculty
"Plan my courses for 2 semesters, I'm interested in AI and applied statistics"
```

## Rust Extension

Entity resolution needs to compare every query against 4,900+ course names. The hot path is Jaro-Winkler string similarity — a character-level algorithm with O(n*m) inner loops that Python handles at ~50ms per 10k pair batch. The Rust implementation (`src/lib.rs`) compiles to a native PyO3 extension (`backend._core`) and runs the same workload in ~2ms.

```
Jaro-Winkler Benchmark — 10,000 string pairs, median of 100 iterations

Implementation         Time    Speedup
──────────────────────────────────────
Python               48.2ms          —
Rust (PyO3)           1.9ms      25.4x
```

The extension is optional. `backend/accel.py` imports the compiled module at startup and falls back to an identical pure-Python implementation if it's missing. The Docker image compiles it at build time; for local development:

```bash
make rust-build    # maturin develop --release (~8 seconds)
make rust-test     # cargo test
make bench         # run the benchmark above
```

## Make Targets

```
make help             Show all targets
make start            Stop everything, then start db + API + frontend
make db               Start databases only (Postgres + Neo4j)
make db-down          Stop databases
make seed             Load courses.json into databases
make serve            Start API locally (databases must be running)
make frontend         Start frontend dev server
make ingest           Run ingestion (optional: make ingest FACULTY="Science")
make pipeline         Run full ingest pipeline (make pipeline FACULTY="Science" DEPT="COMP" FORCE=1)
make up               Start all services via Docker
make down             Stop all Docker services
make rebuild          Rebuild containers from scratch (wipes volumes)
make rebuild-keep     Rebuild containers, keep database volumes
make logs             Tail Docker logs
make rust-build       Build Rust extension (release)
make rust-test        Run Rust unit tests
make bench            Benchmark Rust vs Python jaro_winkler
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
│   ├── ingest/            Ingest → Resolve → Chunk → Embed
│   ├── retrieval/         Keyword + Semantic + Program + Graph → RRF fusion
│   ├── ingestion/         PDF / URL → Extract → Chunk → Embed → Store
│   ├── synthesis/         Chat synthesis + Curriculum assembly
│   └── planner/           Multi-semester curriculum planner (Agent SDK + VLM)
│
├── accel.py        Rust/Python fallback for Jaro-Winkler (PyO3)
├── services/       Stateless domain services (no workflow/lib imports)
│   ├── scraping/          Browser, parser, catalogue, faculty registry
│   ├── resolution/        Entity graph, prerequisites, fuzzy matching
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
| `ingest` | Ingest → resolve → chunk → embed |
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
| `POST /api/v1/courses/batch` | Batch lookup of course details by code |
| `GET /api/v1/programs` | List available programs grouped by faculty |
| `GET /api/v1/plans` | List user's curriculum plans (protected) |
| `POST /api/v1/plans` | Create a plan (auto-populates semesters when program is selected) |
| `GET /api/v1/plans/{id}` | Full plan detail with semesters, documents, linked conversations |
| `PATCH /api/v1/plans/{id}` | Update plan fields (title, status, interests, etc.) |
| `POST /api/v1/plans/{id}/generate` | Trigger AI planner and persist results |
| `POST /api/v1/plans/{id}/semesters` | Add a semester to a plan |
| `PUT /api/v1/plans/{id}/semesters/{sid}` | Update semester courses |
| `POST /api/v1/plans/{id}/documents` | Upload a document (transcript, AP scores, etc.) |
| `POST /api/v1/plans/{id}/conversations/{cid}` | Link a chat conversation to a plan |
| `POST /api/v1/auth/register` | Create a new user account (name + email + password) |
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
mcgill ingest --faculty Science       # Ingest one faculty
mcgill pipeline --dept COMP           # Full pipeline for a department
mcgill pipeline --faculty engineering # Full pipeline (skips already-processed depts)
mcgill pipeline --faculty Science --force  # Re-process all depts even if already done
mcgill seed                           # Load courses.json into databases
mcgill ingest-pdf syllabus.pdf --faculty science  # Ingest a PDF
mcgill curriculum --interests "machine learning" "statistics" --program computer-science
```

## Stack

- **Backend**: Python 3.12, FastAPI, LangGraph, Claude Agent SDK, asyncpg, neo4j, Rust/PyO3 (Jaro-Winkler), Voyage AI, Anthropic
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS 4, Zustand, react-router-dom, D3
- **Databases**: PostgreSQL 17 + pgvector, Neo4j 5
- **Auth**: JWT (PyJWT), bcrypt
- **Infra**: uv, Docker Compose, GitHub Actions CI/CD → GHCR → EC2

## Deployment

Pushing to `main` triggers a GitHub Actions workflow that builds both backend and frontend Docker images, pushes them to GHCR, and deploys to EC2 via SSH. Caddy handles auto-HTTPS via Let's Encrypt for `mcgill.engroff.ai`. The deploy only triggers when relevant files change (`backend/`, `frontend/`, `Dockerfile`, etc.).

**GitHub secrets required** (Settings → Secrets → Actions):

| Secret | Description |
|--------|-------------|
| `EC2_HOST` | EC2 public IP or hostname |
| `EC2_USER` | SSH user (`ubuntu` or `ec2-user`) |
| `EC2_SSH_KEY` | Private SSH key for the instance |

Set `ALLOWED_ORIGINS` in your `.env` to your production domain (e.g. `https://yourdomain.com`) and generate a strong `JWT_SECRET_KEY`.

**EC2 setup** — Docker and docker compose must be installed. Place `docker-compose.prod.yml` and `.env` in `~/mcgill/`, then start databases once:

```bash
cd ~/mcgill
docker compose -f docker-compose.prod.yml up -d postgres neo4j
```

Subsequent pushes to `main` will only replace the `app` and `frontend` containers — databases stay running with their volumes intact.

A separate CI workflow (`ci.yml`) runs ruff lint, mypy type check, and pytest on every push and PR to `main`.

## Tests

122 unit tests covering core functionality with zero external dependencies (no Postgres, Neo4j, or API keys required):

| Module | Tests | Coverage |
|--------|-------|----------|
| `test_parser.py` | 30 | HTML parsing, program page markdown conversion, table rendering, sub-page discovery, variant extraction |
| `test_prerequisites.py` | 13 | Prerequisite/corequisite/restriction extraction, deduplication, self-reference filtering |
| `test_chunker.py` | 20 | Sentence splitting, course chunking with windowing and overlap, program page chunking |
| `test_registry.py` | 30 | Faculty registry, department websites, student resources, foundation page seeds, curriculum interest mapping |
| `test_auth.py` | 25 | Password hashing, JWT, registration, login, chat persistence (4 unit + 21 integration) |
| `test_fdsc_program_retrieval.py` | 17 | End-to-end FDSC program retrieval and synthesis (integration, requires Postgres + Anthropic) |

```bash
make test             # run all tests
```

## Ports

Non-default ports to avoid conflicts with other local services.

| Service        | Port  |
|----------------|-------|
| Frontend (Vite)| 5174  |
| API (FastAPI)  | 8001  |
| PostgreSQL     | 5433  |
| Neo4j Bolt     | 7688  |
| Neo4j Browser  | 7475  |
