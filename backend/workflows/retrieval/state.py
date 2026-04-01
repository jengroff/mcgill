"""Retrieval workflow state — extends BaseWorkflowState."""

from __future__ import annotations

from backend.lib.state import BaseWorkflowState


class RetrievalState(BaseWorkflowState, total=False):
    query: str
    top_k: int
    mode: str  # "keyword" | "semantic" | "hybrid"
    keyword_results: list[dict]
    semantic_results: list[dict]
    program_results: list[dict]
    graph_context: str
    structured_context: str
    fused_results: list[dict]
