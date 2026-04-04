# Changelog

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
