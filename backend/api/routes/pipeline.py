from __future__ import annotations

import asyncio
import logging
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.lib.sse import _sse
from backend.lib.streaming import sse_response

logger = logging.getLogger("backend.api.pipeline")

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

            while seen < len(progress):
                yield _sse(progress[seen])
                seen += 1

            if run.get("status") in ("complete", "error"):
                yield _sse(
                    {
                        "type": "pipeline_done",
                        "status": run["status"],
                        "result": run.get("result", {}),
                    }
                )
                break

            await asyncio.sleep(0.3)

    return sse_response(event_generator())


async def _execute_pipeline(run_id: str, req: PipelineRequest):
    """Delegate pipeline execution to IngestOrchestrator."""
    from backend.workflows.ingest.graph import IngestOrchestrator

    run = _runs[run_id]
    run["status"] = "running"

    orchestrator = IngestOrchestrator()

    def on_event(event: dict):
        run["phase"] = event.get("phase")
        run["progress"].append(event)

    try:
        final_state = await orchestrator.stream(
            on_event=on_event,
            faculty_filter=req.faculty_filter,
            dept_filter=req.dept_filter,
            max_course_pages=req.max_course_pages,
            max_program_pages=req.max_program_pages,
        )
        run["status"] = final_state.get("status", "complete")
        run["result"] = {
            "courses_scraped": final_state.get("courses_scraped", 0),
            "entities_created": final_state.get("entities_created", 0),
            "relationships_created": final_state.get("relationships_created", 0),
            "chunks_created": final_state.get("chunks_created", 0),
        }
    except Exception as e:
        logger.exception("Pipeline execution error")
        run["status"] = "error"
        run["result"] = {"error": str(e)}
