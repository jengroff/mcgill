from __future__ import annotations

from neo4j import AsyncGraphDatabase, AsyncDriver

from backend.config import settings

_driver: AsyncDriver | None = None

CONSTRAINTS = [
    "CREATE CONSTRAINT course_code IF NOT EXISTS FOR (c:Course) REQUIRE c.code IS UNIQUE",
    "CREATE CONSTRAINT dept_code IF NOT EXISTS FOR (d:Department) REQUIRE d.code IS UNIQUE",
    "CREATE CONSTRAINT faculty_slug IF NOT EXISTS FOR (f:Faculty) REQUIRE f.slug IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX course_dept IF NOT EXISTS FOR (c:Course) ON (c.dept)",
]


async def get_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    return _driver


async def init_neo4j() -> None:
    driver = await get_driver()
    async with driver.session() as session:
        for stmt in CONSTRAINTS + INDEXES:
            await session.run(stmt)  # type: ignore[arg-type]


async def close_neo4j() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


async def run_query(query: str, parameters: dict | None = None) -> list[dict]:
    driver = await get_driver()
    async with driver.session() as session:
        result = await session.run(query, parameters or {})  # type: ignore[arg-type]
        return [record.data() async for record in result]
