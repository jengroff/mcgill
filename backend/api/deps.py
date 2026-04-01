"""Dependency injection helpers."""

from __future__ import annotations

import asyncpg

from backend.db.postgres import get_pool


async def get_db() -> asyncpg.Pool:
    return await get_pool()
