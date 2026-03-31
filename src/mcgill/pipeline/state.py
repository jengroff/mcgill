"""LangGraph pipeline state definition."""

from __future__ import annotations

from typing import TypedDict, Annotated
from operator import add


class PipelineState(TypedDict, total=False):
    # Configuration
    faculty_filter: list[str] | None
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

    # Error tracking
    errors: Annotated[list[str], add]

    # Progress callback ID (for SSE streaming)
    run_id: str
