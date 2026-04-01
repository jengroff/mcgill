# No imports from backend.workflows or backend.services — this is the framework layer.

from __future__ import annotations

from typing import AsyncIterator

from fastapi.responses import StreamingResponse


def sse_response(generator: AsyncIterator[str]) -> StreamingResponse:
    """Create a StreamingResponse configured for SSE."""
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
