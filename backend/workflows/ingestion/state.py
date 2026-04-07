from __future__ import annotations

from backend.lib.state import BaseWorkflowState


class IngestionState(BaseWorkflowState, total=False):
    source_type: str  # "pdf" | "url" | "html"
    source_path: str
    source_bytes: bytes
    faculty_slug: str
    raw_text: str
    structured_sections: list[dict]
    chunks: list[str]
    embeddings: list[list[float]]
    chunks_stored: int
