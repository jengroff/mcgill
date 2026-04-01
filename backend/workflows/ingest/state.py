"""Ingest workflow state — extends BaseWorkflowState."""

from __future__ import annotations

from backend.lib.state import BaseWorkflowState


class IngestState(BaseWorkflowState, total=False):
    # Configuration
    faculty_filter: list[str] | None
    dept_filter: list[str] | None
    max_course_pages: int | None
    max_program_pages: int | None

    # Phase 1 output
    courses_scraped: int
    scrape_status: str  # "pending" | "complete" | "error"

    # Phase 2 output
    entities_created: int
    relationships_created: int
    resolve_status: str

    # Phase 3 output
    chunks_created: int
    embed_status: str
