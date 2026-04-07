"""Retrieval workflow nodes — keyword, semantic, program, graph, structured SQL, fusion."""

from __future__ import annotations

import asyncio
import logging
import re
import traceback

from backend.workflows.retrieval.state import RetrievalState

logger = logging.getLogger("backend.workflows.retrieval")


async def keyword_node(state: RetrievalState) -> RetrievalState:
    """Full-text keyword search on courses."""
    try:
        from backend.services.embedding.retrieval import keyword_search

        results = await keyword_search(state["query"], top_k=state.get("top_k", 10))
        return {"keyword_results": results}
    except Exception as e:
        return {
            "keyword_results": [],
            "errors": [f"keyword: {e}\n{traceback.format_exc()}"],
        }


async def semantic_node(state: RetrievalState) -> RetrievalState:
    """Dense vector semantic search on course chunks + program pages.

    Embeds the query once and runs both searches with the shared vector,
    avoiding a redundant Voyage API call.
    """
    try:
        from backend.services.embedding.voyage import embed_query
        from backend.services.embedding.vector_store import (
            search_similar,
            search_similar_programs,
        )

        query_emb = embed_query(state["query"])
        top_k = state.get("top_k", 10)

        course_results, program_results = await asyncio.gather(
            search_similar(query_emb, top_k),
            search_similar_programs(query_emb, 5),
        )
        return {"semantic_results": course_results, "program_results": program_results}
    except Exception as e:
        return {
            "semantic_results": [],
            "program_results": [],
            "errors": [f"semantic: {e}\n{traceback.format_exc()}"],
        }


async def program_node(state: RetrievalState) -> RetrievalState:
    """No-op — program search is handled by semantic_node to share the embedding call."""
    return {}


async def graph_node(state: RetrievalState) -> RetrievalState:
    """Neo4j prerequisite query if course codes detected in query."""
    try:
        codes = re.findall(
            r"\b([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)\b", state["query"].upper()
        )
        if not codes:
            return {"graph_context": ""}

        from backend.db.neo4j import run_query

        code = f"{codes[0][0]} {codes[0][1]}"
        prereqs = await run_query(
            """MATCH (c:Course {code: $code})-[:PREREQUISITE_OF]->(p:Course)
               RETURN p.code AS code, p.title AS title""",
            {"code": code},
        )
        if prereqs:
            ctx = f"Prerequisites for {code}: " + ", ".join(
                f"{r['code']} ({r['title']})" for r in prereqs
            )
            return {"graph_context": ctx}
        return {"graph_context": ""}
    except Exception as e:
        return {
            "graph_context": "",
            "errors": [f"graph: {e}\n{traceback.format_exc()}"],
        }


_DB_SCHEMA = """
Tables:
  faculties (id serial PK, name varchar UNIQUE, slug varchar UNIQUE)
  departments (id serial PK, code varchar(6) UNIQUE, faculty_id int FK→faculties, name varchar, website varchar)
  courses (id serial PK, code varchar UNIQUE, slug varchar, title varchar, dept varchar(6),
           number varchar, credits real, faculty varchar, terms text[],
           description text, prerequisites_raw text, restrictions_raw text, notes_raw text,
           url varchar, name_variants text[], scraped_at timestamptz, updated_at timestamptz)
  course_faculties (course_id int FK→courses, faculty_id int FK→faculties, PK(course_id,faculty_id))
  program_pages (id serial PK, faculty_slug varchar, path varchar UNIQUE, title varchar, content text, scraped_at timestamptz)

Relationships:
  - courses.dept = departments.code (department code, e.g. 'COMP', 'MATH', 'PHIL')
  - departments.faculty_id → faculties.id (each department belongs to one faculty)
  - course_faculties links courses to faculties (many-to-many)
  - courses.faculty is denormalized faculty name (e.g. 'Arts', 'Science', 'Engineering')

Notes:
  - dept is a short code like 'COMP', 'MATH', 'PHIL'
  - faculty is the full name like 'Arts', 'Science', 'Engineering'
  - terms is an array like {'Fall 2025', 'Winter 2026'}
  - credits is real (numeric), e.g. 3.0 or 6.0
  - Use ILIKE for case-insensitive text matching
  - For aggregation queries (counts, top-N, rankings), use GROUP BY with COUNT(*)
  - To count courses per department in a faculty: GROUP BY dept with WHERE faculty ILIKE '%name%'
  - program_pages.content contains markdown-formatted program requirement pages with
    section headings (## Required Courses, ## Elective Courses) and course tables.
    Search with content ILIKE '%COURSE_CODE%' or content ILIKE '%keyword%'.
  - program_pages.path contains URL slugs, e.g. '%food-science%' for FDSC programs.
  - program_pages.faculty_slug groups pages by faculty, e.g. 'agri-env-sci', 'science'.
  - departments.website contains the department's main website URL (e.g. 'https://www.mcgill.ca/foodscience/').
    Join courses.dept = departments.code to look up department websites.
"""


async def structured_node(state: RetrievalState) -> RetrievalState:
    """Text-to-SQL: use Claude to generate a read-only SQL query, execute it, return results."""
    try:
        import anthropic
        from backend.config import settings
        from backend.db.postgres import get_pool

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=(
                "You are a PostgreSQL query generator for a McGill University course database.\n"
                f"{_DB_SCHEMA}\n"
                "Generate a single read-only SELECT query that answers the user's question. "
                "Return ONLY the SQL — no explanation, no markdown, no backticks. "
                "If the question cannot be answered with SQL, return exactly: SKIP"
            ),
            messages=[{"role": "user", "content": state["query"]}],
        )

        sql = response.content[0].text.strip().rstrip(";")  # type: ignore[union-attr]
        if sql == "SKIP" or not sql.upper().startswith("SELECT"):
            return {"structured_context": ""}

        pool = await get_pool()
        async with pool.acquire() as conn:
            # Read-only with timeout for safety
            async with conn.transaction(readonly=True):
                await conn.execute("SET LOCAL statement_timeout = '5s'")
                rows = await conn.fetch(sql)

        if not rows:
            return {
                "structured_context": f"SQL query returned no results.\nQuery: {sql}"
            }

        # Format results as readable text
        columns = list(rows[0].keys())
        lines = [f"SQL results ({len(rows)} rows):"]
        lines.append(" | ".join(columns))
        lines.append("-" * 40)
        for r in rows[:25]:  # Cap at 25 rows
            lines.append(" | ".join(str(r[c]) for c in columns))
        if len(rows) > 25:
            lines.append(f"... and {len(rows) - 25} more rows")

        return {"structured_context": "\n".join(lines)}
    except Exception as e:
        logger.warning(f"Structured query failed: {e}")
        return {"structured_context": ""}


async def fusion_node(state: RetrievalState) -> RetrievalState:
    """Reciprocal rank fusion across keyword + semantic results."""
    try:
        from backend.services.embedding.retrieval import reciprocal_rank_fusion

        fused = reciprocal_rank_fusion(
            state.get("keyword_results", []),
            state.get("semantic_results", []),
            top_n=state.get("top_k", 10),
        )
        return {"fused_results": fused, "status": "complete"}
    except Exception as e:
        # Fall back to whatever results we have
        fallback = state.get("keyword_results", []) or state.get("semantic_results", [])
        return {
            "fused_results": fallback,
            "status": "complete",
            "errors": [f"fusion: {e}"],
        }
