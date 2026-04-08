from __future__ import annotations

from backend.services.lib.state import BaseWorkflowState


class CurriculumState(BaseWorkflowState, total=False):
    student_interests: list[str]
    program_slug: str
    completed_codes: list[str]
    domain_tags: list[str]
    program_requirements: dict
    candidate_courses: list[dict]
    ranked_courses: list[dict]
    conflicts: list[dict]
    recommendation: str
