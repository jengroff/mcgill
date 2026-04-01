# No imports from backend.workflows or backend.services — this is the framework layer.

from __future__ import annotations

from operator import add
from typing import Annotated, TypedDict


class BaseWorkflowState(TypedDict, total=False):
    """Base state that all workflow states must extend."""

    run_id: str
    errors: Annotated[list[str], add]
    status: str  # "pending" | "running" | "complete" | "error"
