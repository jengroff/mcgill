from __future__ import annotations

from backend.services.lib.state import BaseWorkflowState


class PlannerState(BaseWorkflowState, total=False):
    # Input
    plan_id: int | None  # if set, persist results back to this plan
    user_id: int | None
    student_interests: list[str]
    program_slug: str
    completed_codes: list[str]
    target_semesters: int  # number of semesters to plan (e.g. 4 = 2 years)
    pdf_bytes: bytes  # optional uploaded course guide PDF
    pdf_filename: str

    # Populated by gather_context
    guide_pages: list[dict]  # VLM-extracted pages from PDF
    program_requirements: dict  # {required: [...], electives: [...]}
    candidate_courses: list[dict]  # courses from DB matching interests/program
    work_dir: str  # temp directory for SDK agent

    # Output from plan_agent
    plan_markdown: str  # human-readable curriculum plan
    plan_semesters: list[dict]  # structured [{term, courses: [{code, title, credits}]}]
    agent_messages: list[str]  # SDK agent progress messages
