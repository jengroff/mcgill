FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

# Playwright system deps + Chromium
RUN pip install playwright && playwright install --with-deps chromium

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY src/ src/
COPY data/ data/
COPY --from=frontend /frontend/dist frontend/dist

EXPOSE 8000

CMD ["uvicorn", "mcgill.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
