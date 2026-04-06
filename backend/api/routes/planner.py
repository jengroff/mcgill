"""Curriculum planner endpoint — multi-semester planning with optional PDF guide."""

from __future__ import annotations

import logging
from typing import AsyncIterator

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from backend.lib.sse import _sse
from backend.lib.streaming import sse_response

logger = logging.getLogger("backend.api.planner")

router = APIRouter(tags=["Planner"])


class PlannerResponse(BaseModel):
    status: str
    plan_markdown: str
    plan_semesters: list[dict]
    errors: list[str]


@router.post("/planner/plan")
async def plan_curriculum(
    student_interests: str = Form(..., description="Comma-separated interests"),
    program_slug: str = Form("", description="Program slug (e.g. 'computer-science')"),
    completed_codes: str = Form(
        "", description="Comma-separated completed course codes"
    ),
    target_semesters: int = Form(4, description="Number of semesters to plan"),
    guide_pdf: UploadFile | None = File(None, description="Optional PDF course guide"),
):
    """Generate a multi-semester curriculum plan using Claude Agent SDK."""
    from backend.workflows.planner.graph import PlannerOrchestrator

    interests = [s.strip() for s in student_interests.split(",") if s.strip()]
    completed = (
        [s.strip() for s in completed_codes.split(",") if s.strip()]
        if completed_codes
        else []
    )

    pdf_bytes = None
    pdf_filename = ""
    if guide_pdf:
        pdf_bytes = await guide_pdf.read()
        pdf_filename = guide_pdf.filename or "guide.pdf"

    orchestrator = PlannerOrchestrator()
    result = await orchestrator.run(
        student_interests=interests,
        program_slug=program_slug,
        completed_codes=completed,
        target_semesters=target_semesters,
        pdf_bytes=pdf_bytes,
        pdf_filename=pdf_filename,
    )

    return PlannerResponse(
        status=result.get("status", "complete"),
        plan_markdown=result.get("plan_markdown", ""),  # type: ignore[arg-type]
        plan_semesters=result.get("plan_semesters", []),  # type: ignore[arg-type]
        errors=result.get("errors", []),
    )


@router.post("/planner/stream")
async def plan_curriculum_stream(
    student_interests: str = Form(...),
    program_slug: str = Form(""),
    completed_codes: str = Form(""),
    target_semesters: int = Form(4),
    guide_pdf: UploadFile | None = File(None),
):
    """Stream curriculum planning progress via SSE."""
    from backend.workflows.planner.graph import PlannerOrchestrator

    interests = [s.strip() for s in student_interests.split(",") if s.strip()]
    completed = (
        [s.strip() for s in completed_codes.split(",") if s.strip()]
        if completed_codes
        else []
    )

    pdf_bytes = None
    pdf_filename = ""
    if guide_pdf:
        pdf_bytes = await guide_pdf.read()
        pdf_filename = guide_pdf.filename or "guide.pdf"

    orchestrator = PlannerOrchestrator()

    async def event_generator() -> AsyncIterator[str]:
        yield _sse(
            {
                "type": "step_update",
                "phase": "planner",
                "label": "Starting planner",
                "status": "running",
            }
        )

        def on_event(event: dict):
            pass  # events are yielded via stream

        result = await orchestrator.stream(
            on_event=on_event,
            student_interests=interests,
            program_slug=program_slug,
            completed_codes=completed,
            target_semesters=target_semesters,
            pdf_bytes=pdf_bytes,
            pdf_filename=pdf_filename,
        )

        # Stream agent messages
        for msg in result.get("agent_messages", []):  # type: ignore[attr-defined]
            if not msg.startswith("[tool:"):
                yield _sse({"type": "agent_message", "content": msg})

        yield _sse(
            {
                "type": "plan_complete",
                "plan_markdown": result.get("plan_markdown", ""),
                "plan_semesters": result.get("plan_semesters", []),
                "errors": result.get("errors", []),
            }
        )

    return sse_response(event_generator())
