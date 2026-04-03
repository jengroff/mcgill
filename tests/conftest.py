import asyncpg
import pytest_asyncio

from backend.config import settings
import backend.db.postgres as pg_mod


@pytest_asyncio.fixture
async def db():
    """Create a fresh connection pool per test.

    Expects the Docker postgres container running on localhost:5433.
    """
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
