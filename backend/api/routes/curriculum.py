from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("backend.api.curriculum")

router = APIRouter(tags=["Curriculum"])


class CurriculumRequest(BaseModel):
    student_interests: list[str]
    program_slug: str = ""
    completed_codes: list[str] = []


@router.post("/curriculum/recommend")
async def recommend_curriculum(req: CurriculumRequest):
    """Generate curriculum recommendations based on interests and program."""
    from backend.workflows.synthesis.curriculum_graph import CurriculumOrchestrator

    orchestrator = CurriculumOrchestrator()
    result = await orchestrator.run(
        student_interests=req.student_interests,
        program_slug=req.program_slug,
        completed_codes=req.completed_codes,
    )

    return {
        "status": result.get("status", "complete"),
        "ranked_courses": result.get("ranked_courses", []),
        "conflicts": result.get("conflicts", []),
        "recommendation": result.get("recommendation", ""),
        "errors": result.get("errors", []),
    }
