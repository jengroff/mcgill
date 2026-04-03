"""VLM page content types."""

from __future__ import annotations

from typing import TypedDict


class PageContent(TypedDict):
    page_number: int
    text: str
    tables: list[dict]
    layout_type: str  # curriculum_map | course_listing | requirements | prerequisite_chart | general
    confidence: float
