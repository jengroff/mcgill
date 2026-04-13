# Changelog

## 0.13.0 — 2026-04-13

### Changed
- **Concurrent scraping** — all scraping phases (course pages, program pages, advising pages, general info pages) now fetch with a pool of browser pages in parallel instead of one at a time. Default concurrency is 5 pages with a 0.2s inter-request delay (previously sequential with 1s delay). For ~2200 course pages, scraping dropped from ~22 minutes to ~4 minutes. Configurable via `SCRAPER_CONCURRENCY` and `SCRAPER_DELAY_SEC` environment variables
- **Batched Neo4j graph builds** — course node creation, term relationships, faculty cross-listings, and prerequisite edges now use `UNWIND` batching (500 items per query) instead of individual Cypher round-trips per course. Reduces ~6000-10000 Neo4j sessions to ~15 batched queries
- **Batched chunk inserts** — `insert_chunks` and `insert_program_chunks` use `executemany` instead of per-row `execute`, cutting thousands of individual Postgres round-trips to one protocol-level operation per course
- Removed redundant course INSERT loop in `scrape_node` — the scraper already upserts each course during scraping, so the post-scrape re-insert of every course was eliminated

## 0.12.0 — 2026-04-12

### Added
- **Streaming chat responses** — synthesis tokens now stream to the frontend via SSE as they're generated, so users see text appearing within ~1.5 seconds instead of waiting ~10 seconds for the full response
- **Keyword gate on structured_node** — queries that don't need SQL (date lookups, course info, prerequisites) skip the Haiku text-to-SQL call entirely, saving ~1.3 seconds per query

### Changed
- Chat synthesis model switched from Sonnet to Haiku for ~3x faster generation; Sonnet retained for curriculum planner where deeper reasoning matters
- Program page context now prioritized over SQL results and course data in the context window, with adjacent chunk expansion (16-chunk window) so full sections like Fall 2026 key dates reach the LLM intact
- Context budget increased from 8k to 12k chars to accommodate complete academic calendar sections
- Broad important_dates SQL results (>15 rows) discarded automatically — overview questions now answered from the key-dates program page instead of hundreds of administrative date rows
- Synthesis system prompt updated to state dates and deadlines as facts when present in context, eliminating unnecessary hedging

## 0.11.0 — 2026-04-12

### Added
- **Structured important dates scraper** — new Playwright-based scraper interacts with the McGill importantdates Drupal form (sets date range, paginates all result pages), storing each entry with title, start date, and end date in a dedicated `important_dates` table for precise SQL querying
- **`pipeline --general` flag** — `mcgill pipeline --general` (or `make pipeline-general`) runs the full ingest pipeline for university-wide data: scrapes important dates into the structured table, fetches general info pages (academic calendar, enrollment, exams, fees, graduation), then chunks and embeds them for vector search — all independent of any faculty/department pipeline run
- Standalone `scrape` command hidden from CLI help (still works for backwards compatibility); `pipeline` is now the single entry point for all data ingestion
- **Real-time pipeline progress** — the Pipeline Runner UI now streams human-readable status messages (e.g. 'Found 51 course pages to scrape', 'Scraped 51/51 pages') via SSE log events in a scrollable panel

### Changed
- Chat sidebar no longer shows internal 'Pipeline' phase status or random course 'Sources' for non-course queries — these were noise for end users
- Chat text-to-SQL schema now includes the `important_dates` table with usage hints, so the chatbot can answer questions about breaks, holidays, exam periods, and registration deadlines via structured SQL queries
- Removed `importantdates/` from the generic program page scraper (now handled by the dedicated structured scraper; `key-dates` static page retained)

## 0.10.2 — 2026-04-11

### Added
- **User Guide page** — comprehensive `/guide` page accessible from the main nav, documenting Browse & Search, Chat (retrieval pipeline breakdown), Planner (plan creation, semester/course management, document uploads, AI generation, plan-scoped advisor chat), and Pipeline (phases, scope, force re-process)

### Fixed
- **Pipeline SSE disconnect** — added keepalive comments every 15 seconds to the pipeline stream and increased the Vite proxy timeout to 10 minutes, fixing "Lost connection to pipeline stream" errors during long-running scrape/embed phases

## 0.10.1 — 2026-04-11

### Added
- **General university info scraping** — pipeline now scrapes McGill's academic calendar, important dates, exam info, tuition/fees, graduation, and new student pages, storing them as `program_pages` with `faculty_slug="university"` so the chatbot can answer questions about holidays, enrollment deadlines, and other institutional info

## 0.10.0 — 2026-04-11

### Added
- **Pipeline runner UI** — faculty and department pages now have a "Run Pipeline" button that triggers the full ingest pipeline (scrape -> resolve -> chunk -> embed) with real-time phase progress via SSE
- **Force re-process checkbox** — UI toggle next to the pipeline button mirrors `make pipeline FORCE=1`, allowing re-ingestion of already-processed departments
- **`force` flag in pipeline API** — `POST /api/v1/pipeline/run` now accepts a `force` boolean parameter, previously only available via CLI

### Changed
- Medicine & Health Sciences, Education, and Environment faculties are now visible on the browse page (previously hidden)

## 0.9.1 — 2026-04-07

### Changed
- **Bitparallel Jaro-Winkler** — rewrote the Rust implementation from a naive O(n*m) nested loop to a bitparallel algorithm that encodes character positions as `u64` bitmasks, resolving each match with a few bitwise operations instead of scanning the window; 108x faster than pure Python and 2x faster than rapidfuzz (C++)
- Benchmark now includes rapidfuzz (C++) as a third comparison point alongside pure Python and Rust
- Fixed transposition count in Jaro formula to use integer division (matching the standard convention and rapidfuzz's behavior)
- `rapidfuzz` added as a dev dependency for benchmarking

## 0.9.0 — 2026-04-06

### Added
- **Plan auto-population** — selecting a program when creating a plan pre-fills semesters with required courses, credits, and term assignments extracted from scraped program pages
- **Programs listing endpoint** — `GET /api/v1/programs` returns available programs grouped by faculty, derived from the program page registry
- **PlanBuilder service** — extracts program requirements via regex, looks up course credits and term availability, and distributes courses across semesters respecting Fall/Winter scheduling and credit balance
- **Program picker UI** — New Plan form now has faculty and program dropdowns that auto-fill the plan title, plus a start term selector (season + year)
- Management (Desautels) faculty visible on the browse page
- 40 missing department prefixes added to the faculty registry — Mac campus foundation prefixes (AECH, AEPH, AEHM, AEIS), Mac campus departments (AGEC, BTEC, ENTO, FAES, FMTP, SOIL, WILD, WOOD, etc.), cross-faculty departments (BINF, BMDE, EPSC, MIMM, HGEN, PPHS, etc.)

- **Batch course lookup** — `POST /api/v1/courses/batch` accepts a list of codes and returns details (title, credits, terms, description) for all matched courses in one request
- **"Explain Plan" button** — triggers the existing planner workflow (Claude Agent SDK) to generate a rationale for the auto-populated plan, explaining each course's purpose, prerequisite chains, workload balance, and alternatives
- **Rich course display in planner** — semester courses now show title and credits alongside the code, and are clickable links to the full course detail page
- **Advisor chat panel** — right-side panel in the planner with a plan-aware chat that knows the student's courses, semesters, interests, and uploaded documents; powered by the same hybrid retrieval + synthesis pipeline with plan context injected
- **Toast notifications** — all API errors now surface as dismissible toasts in the bottom-right corner with contextual messages and retry buttons where applicable
- **Auth overlay** — login/signup form now renders as a blurred overlay blocking all content until the user authenticates, replacing per-page auth gates

### Changed
- `POST /api/v1/plans` accepts `start_term` parameter and auto-populates semesters when `program_slug` is provided
- Program page chunker keeps markdown tables intact so course requirement lists are retrieved as complete tables instead of fragmented rows
- Planner agent prompt rewritten with a warm, direct advisory voice — explains courses in plain language, flags workload concerns, suggests alternatives, and provides practical registration tips
- Auto-populated plans no longer contain duplicate courses
- Chat `POST /api/v1/chat/ask` accepts optional `plan_id` to scope the conversation with full plan context (semesters, courses, documents)
- Synthesis pipeline includes `plan_context` when chat is scoped to a curriculum plan

## 0.8.0 — 2026-04-06

### Added
- **Planner page** — dedicated UI for creating, editing, and managing curriculum plans with a three-panel layout (plan list, semester grid, document drawer)
- **Plan persistence** — `plans`, `plan_semesters`, `plan_documents`, `plan_conversations` tables store curriculum plans as first-class entities with semester-by-semester course assignments
- **Plan CRUD API** — full REST endpoints for plans (`/api/v1/plans`), semesters, document upload, and conversation linking
- **Plan document repository** — upload transcripts, AP score reports, and course guides per plan; PDF text is auto-extracted on upload
- **Plan generation endpoint** — `POST /api/v1/plans/{id}/generate` triggers the planner workflow and persists structured results (semesters + courses) back to the plan
- **Planner workflow persistence** — `persist_plan_node` saves agent output (markdown + structured semesters) to the plans table after generation
- **Planner nav link** in header with CalendarDays icon
- Food chemistry and food science added to curriculum interest mapping

### Changed
- Planner graph now runs 3 nodes: gather_context → plan_agent → persist_plan
- `PlannerState` accepts `plan_id` and `user_id` for plan-scoped generation

## 0.7.0 — 2026-04-06

### Added
- Department website URLs — `departments` table now stores a `website` column populated from a static mapping of ~60 McGill department URLs
- Department and faculty student resources layer — student societies, library subject guides, advisor contacts, and foundation year emails injected into synthesis context
- Foundation Year program seed URLs added to scraper for Ag & Env Sci, Science, Arts, and Arts & Science faculties — the scraper now explicitly captures Foundation Program course listings instead of relying on sub-page discovery
- Arts & Science faculty added to `PROGRAM_PAGES` with foundation year URLs
- Synthesis prompt updated with AP/IB/A-Level exemption awareness, actionable advisor contacts, and foundation year program handling
- Department `website` field exposed in `GET /api/v1/faculties/{slug}/departments` responses
- SSE connection established on app load so Live indicator is active on all tabs, not just Chat
- UI-only faculty filtering — Education, Law, Nursing, Management, Environment, Dental, and Medicine hidden from the browse page

### Changed
- Pipeline (`resolve_node`) now populates Postgres `faculties` and `departments` tables directly from the registry — seeding is no longer a prerequisite for department data
- Department website lookup in synthesis uses the static mapping directly instead of querying the DB
- Text-to-SQL schema description updated to include `departments.website` for structured queries
- `seed_from_json` migration populates department website URLs on seed
- SSE connection moved from `ChatPanel` to `App.tsx` for app-wide availability
- Auto-migration adds `departments.website` column on startup for existing databases
- Test suite expanded from 4 → 122 passing unit tests covering parser, prerequisite resolution, chunking, faculty registry, curriculum interest mapping, and student resources

## 0.6.0 — 2026-04-06

### Added
- Rust-accelerated Jaro-Winkler string similarity via PyO3 with pure-Python fallback (`backend/accel.py`)
- `benchmark.py` for measuring Rust vs pure Python fuzzy matching performance
- Makefile targets `rust-build`, `rust-test`, `bench` for Rust development workflow

### Changed
- Replaced `rapidfuzz` dependency with self-contained Rust + Python Jaro-Winkler implementation
- Build system switched to maturin for native extension support
- CI installs Rust toolchain and enforces minimum 20% test coverage (`--cov-fail-under=20`)
- Deploy workflow triggers on `src/**` and `Cargo.toml` changes

## 0.5.0 — 2026-04-05

### Added
- MIT license
- `ALLOWED_ORIGINS` environment variable for configurable CORS origins
- `JWT_SECRET_KEY` and `ALLOWED_ORIGINS` entries in `.env.example`
- Fork checklist in `docker-compose.prod.yml` header comment

### Changed
- Replaced `ty` type checker with `mypy` — pre-commit hook, CI workflow, and dev dependencies updated
- CORS origins are now read from `ALLOWED_ORIGINS` env var instead of being hardcoded
- Removed internal integration docs (Stroma, Stanchion) that referenced private projects
- FastAPI app version now stays in sync with `pyproject.toml`

## 0.4.0 — 2026-04-04

### Added
- Login/signup prompt on first visit — new users must create an account (name + email + password) before browsing
- `name` field on user accounts, displayed as a personalized greeting ("Welcome back, {name}") on the browse page
- Example prompts on the auth screen to help new users understand what they can ask
- User's first name and logout button shown in the header
- Token persistence via localStorage with auto-restore on page reload
- Frontend sends Authorization header on chat and session requests
- Frontend container in production stack — separate GHCR image built and deployed alongside the backend
- Caddy reverse proxy with auto-HTTPS (Let's Encrypt) for `mcgill.engroff.ai`
- DNS config (`8.8.8.8`, `1.1.1.1`) on Caddy container for Let's Encrypt resolution on EC2
- CI workflow (`ci.yml`) with ruff lint, ty type check, and pytest across Python 3.12 + 3.13
- Pre-commit hooks: ruff fix + format, standard checks, ty type check
- `ruff`, `ty`, `pre-commit` added to dev dependencies
- Fuzzy faculty name matching in pipeline pre-check (substring fallback for partial names)
- Error when pipeline faculty filter matches nothing (instead of silently reporting "all done")

### Changed
- Retrieval fan-out is now parallel — keyword, semantic, graph, and structured queries run concurrently via `asyncio.gather`, cutting ~1–2s from response time
- Semantic and program search share a single Voyage API embedding call instead of two separate calls
- Deploy workflow only triggers on changes to `backend/`, `frontend/`, `Dockerfile`, `docker-compose.prod.yml`, `Caddyfile`, `pyproject.toml`, or `uv.lock`
- Deploy workflow builds and pushes both app and frontend images to GHCR
- Scrape buttons removed from header, faculty page, and department page (pipeline is still available via chat or CLI)
- Correct GHCR image reference (`ghcr.io/jengroff/mcgill`)

## 0.3.0 — 2026-04-03

### Added
- Per-department pre-check in the ingest pipeline — departments that already have embedded chunks are skipped automatically
- `--force` flag on `mcgill pipeline` to re-process departments even if already pipelined
- `FORCE=1` option on `make pipeline`

### Changed
- Resolve and embed stages now scope to the target departments instead of processing all courses in the DB
- Pipeline prints skipped departments and a hint to use `--force` when everything is already processed

## 0.2.0 — 2026-04-03

### Added
- User registration and login with email + password (bcrypt hashing, JWT tokens)
- `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/me` endpoints
- Persistent chat memory — authenticated users' conversations and messages are stored in postgres across sessions
- `/api/v1/chat/conversations` and `/api/v1/chat/conversations/{id}/messages` endpoints for retrieving conversation history
- Session resumption — POST a `session_id` to `/api/v1/chat/session` to reload a prior conversation
- Auto-generated conversation titles from the first user message
- CI/CD pipeline via GitHub Actions — builds Docker image on push to `main`, pushes to GHCR, deploys to EC2 via SSH
- `docker-compose.prod.yml` for production deployment (no exposed DB ports, `restart: unless-stopped`)
- `make deploy-setup` target showing required GitHub secrets
- `users`, `conversations`, `messages` tables in postgres DDL
- Test suite for auth and chat persistence (25 tests)

### Changed
- Chat endpoints now accept optional JWT auth — anonymous usage still works without persistence

## 0.1.0

Initial release with scraping, resolution, embedding, retrieval, synthesis, curriculum planning, and PDF ingestion workflows.
