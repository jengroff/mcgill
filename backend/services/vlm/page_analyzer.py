from __future__ import annotations

import logging

from backend.services.vlm.types import PageContent

logger = logging.getLogger(__name__)

_KEYWORD_MAP: dict[str, list[str]] = {
    "curriculum_map": [
        "year 1",
        "year 2",
        "semester",
        "fall",
        "winter",
        "u0",
        "u1",
        "u2",
        "u3",
    ],
    "course_listing": ["credits", "3 credits", "offered", "instructor", "lecture"],
    "requirements": [
        "required",
        "complementary",
        "elective",
        "core courses",
        "minimum",
    ],
    "prerequisite_chart": ["prerequisite", "corequisite", "restriction", "permission"],
}


class PageAnalyzer:
    def analyze(self, page_data: dict) -> PageContent:
        text = page_data.get("text", "").lower()
        layout_type = self._detect_layout(text)
        return PageContent(
            page_number=page_data.get("page_number", 0),
            text=page_data.get("text", ""),
            tables=page_data.get("tables", []),
            layout_type=layout_type,
            confidence=0.3,
        )

    def _detect_layout(self, text: str) -> str:
        scores: dict[str, int] = {}
        for layout, keywords in _KEYWORD_MAP.items():
            scores[layout] = sum(1 for kw in keywords if kw in text)
        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] > 0 else "general"
