"""Pipeline trigger and status endpoints — also supports SSE progress streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("mcgill.api.pipeline")

router = APIRouter(tags=["Pipeline"])

# In-memory pipeline run tracking
_runs: dict[str, dict] = {}


class PipelineRequest(BaseModel):
    faculty_filter: list[str] | None = None
    dept_filter: list[str] | None = None
    max_course_pages: int | None = None
    max_program_pages: int | None = None


@router.post("/pipeline/run")
async def trigger_pipeline(req: PipelineRequest):
    run_id = str(uuid.uuid4())
    _runs[run_id] = {
        "status": "pending",
        "phase": None,
        "progress": [],
        "config": req.model_dump(),
    }

    # Run pipeline in background
    asyncio.create_task(_execute_pipeline(run_id, req))

    return {"run_id": run_id, "status": "pending"}


@router.get("/pipeline/status/{run_id}")
async def pipeline_status(run_id: str):
    run = _runs.get(run_id)
    if not run:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return run


@router.get("/pipeline/stream/{run_id}")
async def pipeline_stream(run_id: str, request: Request):
    """SSE stream of pipeline progress events."""
    if run_id not in _runs:
        _runs[run_id] = {"status": "unknown", "phase": None, "progress": []}

    seen = 0

    async def event_generator() -> AsyncIterator[str]:
        nonlocal seen
        yield _sse({"type": "pipeline_started", "run_id": run_id})

        while not await request.is_disconnected():
            run = _runs.get(run_id, {})
            progress = run.get("progress", [])

            # Send any new progress events
            while seen < len(progress):
                yield _sse(progress[seen])
                seen += 1

            if run.get("status") in ("complete", "error"):
                yield _sse({
                    "type": "pipeline_done",
                    "status": run["status"],
                    "result": run.get("result", {}),
                })
                break

            await asyncio.sleep(0.3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _execute_pipeline(run_id: str, req: PipelineRequest):
    """Execute the LangGraph pipeline with progress tracking."""
    run = _runs[run_id]

    def on_progress(phase: str, msg: str, current: int, total: int):
        run["phase"] = phase
        run["progress"].append({
            "type": "step_update",
            "phase": phase,
            "message": msg,
            "current": current,
            "total": total,
        })

    try:
        run["status"] = "running"

        # Phase 1: Scrape
        run["phase"] = "scrape"
        on_progress("scrape", "Starting scraper...", 0, 0)

        from mcgill.scraper.catalogue import run as run_scrape
        courses = await run_scrape(
            faculty_filter=req.faculty_filter,
            dept_filter=req.dept_filter,
            max_course_pages=req.max_course_pages,
            max_program_pages=req.max_program_pages,
            on_progress=on_progress,
        )

        # Phase 2: Resolve
        run["phase"] = "resolve"
        on_progress("resolve", "Building entity graph...", 0, 0)

        from mcgill.resolver.entity_graph import build_faculty_nodes, build_course_nodes, build_relationships
        from mcgill.resolver.prerequisites import parse_prerequisites

        await build_faculty_nodes()
        entity_count = await build_course_nodes(courses)
        on_progress("resolve", f"Created {entity_count} course nodes", entity_count, entity_count)

        known_codes = {c.code for c in courses}
        all_refs = []
        for c in courses:
            refs = parse_prerequisites(c.code, c.prerequisites_raw, c.restrictions_raw, known_codes)
            all_refs.extend(refs)

        rel_count = await build_relationships(all_refs)
        on_progress("resolve", f"Created {rel_count} relationships", rel_count, rel_count)

        # Phase 3: Embed
        run["phase"] = "embed"
        on_progress("embed", "Generating embeddings...", 0, 0)

        from mcgill.embeddings.chunker import chunk_course, chunk_program_page
        from mcgill.embeddings.voyage import embed_texts
        from mcgill.embeddings.vector_store import insert_chunks, insert_program_chunks, create_ivfflat_index
        from mcgill.db.postgres import get_pool

        pool = await get_pool()

        # 3a: Embed course chunks
        scraped_codes = [c.code for c in courses]
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, code, title, description, prerequisites_raw,
                          restrictions_raw, notes_raw, dept, faculty
                   FROM courses WHERE code = ANY($1)""",
                scraped_codes,
            )

        batch_texts: list[str] = []
        batch_meta: list[tuple[int, int]] = []

        for r in rows:
            chunks = chunk_course(
                code=r["code"], title=r["title"],
                description=r["description"] or "",
                prerequisites_raw=r["prerequisites_raw"] or "",
                restrictions_raw=r["restrictions_raw"] or "",
                notes_raw=r["notes_raw"] or "",
                dept=r["dept"] or "",
                faculty=r["faculty"] or "",
            )
            batch_meta.append((r["id"], len(batch_texts)))
            batch_texts.extend(chunks)

        on_progress("embed", f"Embedding {len(batch_texts)} course chunks...", 0, len(batch_texts))

        total_course_chunks = 0
        if batch_texts:
            all_embeddings = embed_texts(batch_texts)

            for i, (course_id, start_idx) in enumerate(batch_meta):
                end_idx = batch_meta[i + 1][1] if i + 1 < len(batch_meta) else len(batch_texts)
                course_chunks = batch_texts[start_idx:end_idx]
                course_embs = all_embeddings[start_idx:end_idx]
                total_course_chunks += await insert_chunks(course_id, course_chunks, course_embs)

        on_progress("embed", f"Stored {total_course_chunks} course chunks", total_course_chunks, total_course_chunks)

        # 3b: Embed program page chunks
        async with pool.acquire() as conn:
            prog_rows = await conn.fetch(
                "SELECT id, title, content, faculty_slug FROM program_pages"
            )

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

        total_prog_chunks = 0
        if prog_texts:
            on_progress("embed", f"Embedding {len(prog_texts)} program chunks...", 0, len(prog_texts))
            prog_embeddings = embed_texts(prog_texts)

            for i, (page_id, start_idx) in enumerate(prog_meta):
                end_idx = prog_meta[i + 1][1] if i + 1 < len(prog_meta) else len(prog_texts)
                page_chunks = prog_texts[start_idx:end_idx]
                page_embs = prog_embeddings[start_idx:end_idx]
                total_prog_chunks += await insert_program_chunks(page_id, page_chunks, page_embs)

        await create_ivfflat_index()
        on_progress("embed", f"Stored {total_course_chunks} course + {total_prog_chunks} program chunks", 0, 0)

        run["status"] = "complete"
        run["result"] = {
            "courses_scraped": len(courses),
            "entities_created": entity_count,
            "relationships_created": rel_count,
            "course_chunks_embedded": total_course_chunks,
            "program_chunks_embedded": total_prog_chunks,
        }

    except Exception as e:
        logger.exception("Pipeline execution error")
        run["status"] = "error"
        run["result"] = {"error": str(e)}
        on_progress("error", str(e), 0, 0)


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"
