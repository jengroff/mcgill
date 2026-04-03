"""Claude Vision analyzer for McGill course guide pages."""

from __future__ import annotations

import base64
import json
import logging
import re

import anthropic

from backend.config import settings
from backend.services.vlm.types import PageContent

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """Analyze this McGill University course guide page and extract structured data.

Return JSON with this exact structure:
{
    "text": "full text content preserving course codes, credit counts, and prerequisites",
    "tables": [
        {
            "headers": ["col1", "col2"],
            "rows": [["val1", "val2"]]
        }
    ],
    "layout_type": "one of: curriculum_map | course_listing | requirements | prerequisite_chart | general"
}

Extraction guidelines:
- Preserve course codes exactly (e.g. "COMP 250", "MATH 240")
- Extract credit values (e.g. "3 credits", "3-6 credits")
- Capture prerequisite relationships (e.g. "Prerequisite: COMP 202")
- For tables: preserve column headers exactly, include all data rows
- For flowcharts or prerequisite diagrams: describe the relationships as text
- Classify layout_type:
    curriculum_map = visual flowchart or semester-by-semester layout
    course_listing = list of courses with descriptions
    requirements = degree requirements, required vs elective courses
    prerequisite_chart = prerequisite chain diagram or table
    general = other academic content"""


class ClaudeVisionAnalyzer:
    def __init__(self, model: str | None = None):
        self.model = model or settings.claude_model

    def analyze_page_image(
        self,
        image_bytes: bytes,
        page_number: int,
        media_type: str = "image/png",
    ) -> PageContent:
        b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64,
                                },
                            },
                            {"type": "text", "text": _EXTRACTION_PROMPT},
                        ],
                    }
                ],
            )
            raw = response.content[0].text
            data = self._parse_json_response(raw)

            tables = data.get("tables", [])
            confidence = self._compute_confidence(data, tables)
            layout = data.get("layout_type", "general")
            logger.info(
                "VLM page %s — layout=%s confidence=%.2f text=%d chars tables=%d",
                page_number, layout, confidence, len(data.get("text", "")), len(tables),
            )

            return PageContent(
                page_number=page_number,
                text=data.get("text", ""),
                tables=tables,
                layout_type=layout,
                confidence=confidence,
            )
        except (
            anthropic.AuthenticationError,
            anthropic.PermissionDeniedError,
            anthropic.BadRequestError,
        ):
            raise
        except Exception:
            logger.exception("VLM analysis failed for page %s", page_number)
            return PageContent(
                page_number=page_number,
                text="",
                tables=[],
                layout_type="general",
                confidence=0.0,
            )

    def _parse_json_response(self, raw: str) -> dict:
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
        cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            logger.warning("Failed to parse VLM JSON response")
            return {"text": raw, "tables": [], "layout_type": "general"}

    def _compute_confidence(self, data: dict, tables: list) -> float:
        non_null = sum(1 for v in data.values() if v)
        table_bonus = len(tables) * 0.1
        raw_score = (non_null / max(len(data), 1)) + table_bonus
        return min(raw_score, 1.0)
