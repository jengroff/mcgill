import os
import socket

import asyncpg
import pytest
import pytest_asyncio

from backend.config import settings
import backend.db.postgres as pg_mod


def _postgres_reachable() -> bool:
    """Quick TCP check against the Postgres port (no async needed)."""
    host = "localhost"
    port = 5433
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


requires_postgres = pytest.mark.skipif(
    not _postgres_reachable(),
    reason="Postgres not reachable on localhost:5433",
)

requires_anthropic = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY") and not settings.anthropic_api_key,
    reason="ANTHROPIC_API_KEY not set",
)


@pytest_asyncio.fixture
async def db():
    """Create a fresh connection pool per test.

    Expects the Docker postgres container running on localhost:5433.
    """
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable on localhost:5433")
    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=3)
    yield pool
    await pool.close()


@pytest_asyncio.fixture(autouse=True)
async def reset_global_pool():
    """Reset the global asyncpg pool before each test so that
    orchestrators (which call ``get_pool()``) get a pool bound to the
    current event loop instead of a stale one from a prior test.
    """
    if pg_mod._pool is not None:
        try:
            await pg_mod._pool.close()
        except Exception:
            pass
        pg_mod._pool = None
    yield
    if pg_mod._pool is not None:
        try:
            await pg_mod._pool.close()
        except Exception:
            pass
        pg_mod._pool = None
