"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health():
    pg_status = "unknown"
    neo4j_status = "unknown"

    try:
        from backend.db.postgres import get_pool

        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        pg_status = "connected"
    except Exception:
        pg_status = "disconnected"

    try:
        from backend.db.neo4j import run_query

        await run_query("RETURN 1 AS n")
        neo4j_status = "connected"
    except Exception:
        neo4j_status = "disconnected"

    return {
        "status": "ok"
        if pg_status == "connected" and neo4j_status == "connected"
        else "degraded",
        "postgres": pg_status,
        "neo4j": neo4j_status,
    }
