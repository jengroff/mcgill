"""PDF / URL ingestion endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, UploadFile, File, Form

from backend.lib.sse import _sse
from backend.lib.streaming import sse_response

logger = logging.getLogger("backend.api.ingestion")

router = APIRouter(tags=["Ingestion"])


@router.post("/ingest/pdf")
async def ingest_pdf(
    file: UploadFile = File(...),
    faculty_slug: str = Form(""),
):
    """Accept a PDF upload, run ingestion workflow, return result."""
    from backend.workflows.ingestion.graph import IngestionOrchestrator

    pdf_bytes = await file.read()
    orchestrator = IngestionOrchestrator()

    def on_event(event: dict):
        pass  # TODO: wire up SSE streaming for progress

    result = await orchestrator.run(
        source_type="pdf",
        source_path=file.filename or "upload.pdf",
        source_bytes=pdf_bytes,
        faculty_slug=faculty_slug,
    )

    return {
        "status": result.get("status", "complete"),
        "chunks_stored": result.get("chunks_stored", 0),
        "errors": result.get("errors", []),
    }
