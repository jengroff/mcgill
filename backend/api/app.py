"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings

logger = logging.getLogger("backend.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from backend.db.postgres import init_db, close_db
    from backend.db.neo4j import init_neo4j, close_neo4j

    logger.info("McGill API starting up")
    import backend.workflows  # noqa: F401 — triggers workflow registration

    await init_db()
    await init_neo4j()
    yield
    await close_db()
    await close_neo4j()
    logger.info("McGill API shut down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="McGill Course Explorer API",
        description="Scrape, resolve, embed, and query McGill University course data",
        version="0.5.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
    )

    if settings.allowed_origins:
        origins = [o.strip() for o in settings.allowed_origins.split(",")]
    elif settings.is_development:
        origins = ["*"]
    else:
        origins = ["http://localhost:5173", "http://localhost:3000"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from backend.api.routes.health import router as health_router
    from backend.api.routes.faculties import router as faculties_router
    from backend.api.routes.courses import router as courses_router
    from backend.api.routes.search import router as search_router
    from backend.api.routes.pipeline import router as pipeline_router
    from backend.api.routes.auth import router as auth_router
    from backend.api.routes.chat import router as chat_router
    from backend.api.routes.ingestion import router as ingestion_router
    from backend.api.routes.curriculum import router as curriculum_router
    from backend.api.routes.planner import router as planner_router
    from backend.api.routes.plans import router as plans_router

    app.include_router(health_router)
    app.include_router(auth_router, prefix="/api/v1/auth")
    app.include_router(faculties_router, prefix="/api/v1")
    app.include_router(courses_router, prefix="/api/v1")
    app.include_router(search_router, prefix="/api/v1")
    app.include_router(pipeline_router, prefix="/api/v1")
    app.include_router(chat_router, prefix="/api/v1/chat")
    app.include_router(ingestion_router, prefix="/api/v1")
    app.include_router(curriculum_router, prefix="/api/v1")
    app.include_router(planner_router, prefix="/api/v1")
    app.include_router(plans_router, prefix="/api/v1")

    # Serve frontend static files if built
    static_dir = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"
    if static_dir.is_dir():
        app.mount(
            "/", StaticFiles(directory=str(static_dir), html=True), name="frontend"
        )

    return app
