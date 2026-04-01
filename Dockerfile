FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (cached until pyproject.toml or uv.lock change)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Copy source and install the project itself
COPY backend/ backend/
RUN uv sync --frozen --no-editable

# Playwright system deps + Chromium
RUN uv run playwright install --with-deps chromium

COPY data/ data/
COPY --from=frontend /frontend/dist frontend/dist

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "backend.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
