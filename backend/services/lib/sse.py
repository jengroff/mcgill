# No imports from backend.workflows or backend.services — this is the framework layer.

from __future__ import annotations

import json


def _sse(data: dict) -> str:
    """Format a dict as a Server-Sent Event data line."""
    return f"data: {json.dumps(data)}\n\n"


def progress_event(phase: str, message: str, current: int = 0, total: int = 0) -> str:
    return _sse(
        {
            "type": "step_update",
            "phase": phase,
            "message": message,
            "current": current,
            "total": total,
        }
    )


def error_event(message: str) -> str:
    return _sse({"type": "error", "message": message})


def done_event(result: dict) -> str:
    return _sse({"type": "pipeline_done", "status": "complete", "result": result})
