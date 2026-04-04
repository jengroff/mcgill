from __future__ import annotations

import json
import logging
import traceback
from pathlib import Path

from backend.workflows.ingest.state import IngestState

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


async def precheck_node(state: IngestState) -> IngestState:
    """Determine which departments need processing by checking for existing embeddings.

    A department is considered "pipeline-complete" if it has at least one course
    with a row in `course_chunks`. Departments that are already complete get
    skipped unless `force=True`.
    """
    try:
        from backend.db.postgres import get_pool
        from backend.services.scraping.faculties import ALL_FACULTIES, get_active_faculties

        force = state.get("force", False)
        faculty_filter = state.get("faculty_filter")
        dept_filter = state.get("dept_filter")

        # Resolve the target department codes
        if dept_filter:
            target_depts = [d.upper() for d in dept_filter]
        elif faculty_filter:
            active = get_active_faculties(faculty_filter)
            target_depts = [p for _, _, prefixes in active for p in prefixes]
        else:
            target_depts = [p for _, _, prefixes in ALL_FACULTIES for p in prefixes]

        if force:
            logger.info("Force flag set — processing all %d departments", len(target_depts))
            return {
                "skipped_depts": [],
                "active_depts": target_depts,
            }

        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT DISTINCT c.dept FROM courses c
                   JOIN course_chunks cc ON cc.course_id = c.id
                   WHERE c.dept = ANY($1)""",
                target_depts,
            )
        completed = {r["dept"] for r in rows}

        active = [d for d in target_depts if d not in completed]
        skipped = [d for d in target_depts if d in completed]

        if skipped:
            logger.info(
                "Skipping %d already-processed departments: %s",
                len(skipped), ", ".join(sorted(skipped)),
            )
        if active:
            logger.info(
                "Processing %d departments: %s",
                len(active), ", ".join(sorted(active)),
            )

        return {
            "skipped_depts": skipped,
            "active_depts": active,
        }
    except Exception as e:
        return {
            "scrape_status": "error",
            "errors": [f"precheck: {e}\n{traceback.format_exc()}"],
            "skipped_depts": [],
            "active_depts": [],
        }


async def scrape_node(state: IngestState) -> IngestState:
    """Phase 1: Scrape course catalogue.

    Uses `active_depts` from the pre-check node to scrape only departments
    that haven't been processed yet.
    """
    try:
        from backend.services.scraping.catalogue import run as run_scrape

        active_depts = state.get("active_depts")
        courses = await run_scrape(
            faculty_filter=state.get("faculty_filter") if not active_depts else None,
            dept_filter=active_depts or state.get("dept_filter"),
            max_course_pages=state.get("max_course_pages"),
            max_program_pages=state.get("max_program_pages"),
        )

        # Also insert into PostgreSQL
        from backend.db.postgres import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            for c in courses:
                await conn.execute(
                    """INSERT INTO courses (code, slug, title, dept, number, credits,
                           faculty, terms, description, prerequisites_raw,
                           restrictions_raw, notes_raw, url, name_variants)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                       ON CONFLICT (code) DO UPDATE SET
                           title = EXCLUDED.title,
                           description = EXCLUDED.description,
                           prerequisites_raw = EXCLUDED.prerequisites_raw,
                           restrictions_raw = EXCLUDED.restrictions_raw,
                           terms = EXCLUDED.terms,
                           updated_at = now()""",
                    c.code, c.slug, c.title, c.dept, c.number,
                    c.credits, c.faculty, c.terms, c.description,
                    c.prerequisites_raw, c.restrictions_raw,
                    c.notes_raw, c.url, c.name_variants,
                )

        return {
            "courses_scraped": len(courses),
            "scrape_status": "complete",
        }
    except Exception as e:
        return {
            "scrape_status": "error",
            "errors": [f"scrape: {e}\n{traceback.format_exc()}"],
        }


async def resolve_node(state: IngestState) -> IngestState:
    """Phase 2: Entity resolution and Neo4j graph build."""
    try:
        from backend.db.postgres import get_pool
        from backend.models.course import CourseCreate
        from backend.services.resolution.prerequisites import parse_prerequisites
        from backend.services.resolution.entity_graph import (
            build_faculty_nodes,
            build_course_nodes,
            build_relationships,
        )

        pool = await get_pool()
        active_depts = state.get("active_depts")

        async with pool.acquire() as conn:
            if active_depts:
                rows = await conn.fetch(
                    "SELECT * FROM courses WHERE dept = ANY($1)", active_depts,
                )
            else:
                rows = await conn.fetch("SELECT * FROM courses")

        courses = [
            CourseCreate(
                code=r["code"], slug=r["slug"], title=r["title"],
                dept=r["dept"], number=r["number"], credits=r["credits"],
                faculty=r["faculty"], faculties=[], terms=r["terms"] or [],
                description=r["description"] or "",
                prerequisites_raw=r["prerequisites_raw"] or "",
                restrictions_raw=r["restrictions_raw"] or "",
                notes_raw=r["notes_raw"] or "",
                url=r["url"] or "",
                name_variants=r["name_variants"] or [],
            )
            for r in rows
        ]

        known_codes = {c.code for c in courses}

        # Build faculty and department nodes
        await build_faculty_nodes()

        # Build course nodes
        entity_count = await build_course_nodes(courses)

        # Parse and build prerequisite relationships
        all_refs = []
        for c in courses:
            refs = parse_prerequisites(
                c.code, c.prerequisites_raw, c.restrictions_raw, known_codes
            )
            all_refs.extend(refs)

        rel_count = await build_relationships(all_refs)

        return {
            "entities_created": entity_count,
            "relationships_created": rel_count,
            "resolve_status": "complete",
        }
    except Exception as e:
        return {
            "resolve_status": "error",
            "errors": [f"resolve: {e}\n{traceback.format_exc()}"],
        }


async def embed_node(state: IngestState) -> IngestState:
    """Phase 3: Generate embeddings and store in pgvector."""
    try:
        from backend.db.postgres import get_pool
        from backend.services.embedding.chunker import chunk_course, chunk_program_page
        from backend.services.embedding.voyage import embed_texts
        from backend.services.embedding.vector_store import insert_chunks, insert_program_chunks, create_ivfflat_index

        pool = await get_pool()
        active_depts = state.get("active_depts")

        # --- Course chunks ---
        async with pool.acquire() as conn:
            if active_depts:
                rows = await conn.fetch(
                    """SELECT id, code, title, description, prerequisites_raw,
                              restrictions_raw, notes_raw, dept, faculty
                       FROM courses WHERE dept = ANY($1)""",
                    active_depts,
                )
            else:
                rows = await conn.fetch(
                    """SELECT id, code, title, description, prerequisites_raw,
                              restrictions_raw, notes_raw, dept, faculty
                       FROM courses"""
                )

        total_course_chunks = 0
        batch_texts: list[str] = []
        batch_meta: list[tuple[int, int]] = []  # (course_id, chunk_start_idx)

        for r in rows:
            chunks = chunk_course(
                code=r["code"],
                title=r["title"],
                description=r["description"] or "",
                prerequisites_raw=r["prerequisites_raw"] or "",
                restrictions_raw=r["restrictions_raw"] or "",
                notes_raw=r["notes_raw"] or "",
                dept=r["dept"] or "",
                faculty=r["faculty"] or "",
            )
            batch_meta.append((r["id"], len(batch_texts)))
            batch_texts.extend(chunks)

        if batch_texts:
            all_embeddings = embed_texts(batch_texts)

            for i, (course_id, start_idx) in enumerate(batch_meta):
                end_idx = batch_meta[i + 1][1] if i + 1 < len(batch_meta) else len(batch_texts)
                course_chunks = batch_texts[start_idx:end_idx]
                course_embs = all_embeddings[start_idx:end_idx]
                total_course_chunks += await insert_chunks(course_id, course_chunks, course_embs)

        # --- Program page chunks ---
        async with pool.acquire() as conn:
            prog_rows = await conn.fetch(
                "SELECT id, title, content, faculty_slug FROM program_pages"
            )

        total_prog_chunks = 0
        prog_texts: list[str] = []
        prog_meta: list[tuple[int, int]] = []

        for r in prog_rows:
            chunks = chunk_program_page(
                title=r["title"] or "",
                content=r["content"] or "",
                faculty_slug=r["faculty_slug"] or "",
            )
            if chunks:
                prog_meta.append((r["id"], len(prog_texts)))
                prog_texts.extend(chunks)

        if prog_texts:
            prog_embeddings = embed_texts(prog_texts)

            for i, (page_id, start_idx) in enumerate(prog_meta):
                end_idx = prog_meta[i + 1][1] if i + 1 < len(prog_meta) else len(prog_texts)
                page_chunks = prog_texts[start_idx:end_idx]
                page_embs = prog_embeddings[start_idx:end_idx]
                total_prog_chunks += await insert_program_chunks(page_id, page_chunks, page_embs)

        await create_ivfflat_index()

        return {
            "chunks_created": total_course_chunks + total_prog_chunks,
            "embed_status": "complete",
        }
    except Exception as e:
        return {
            "embed_status": "error",
            "errors": [f"embed: {e}\n{traceback.format_exc()}"],
        }
