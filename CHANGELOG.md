# Changelog

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
