from __future__ import annotations

from backend.lib.state import BaseWorkflowState


class SynthesisState(BaseWorkflowState, total=False):
    query: str
    session_id: str
    conversation_history: list[dict]
    retrieval_context: list[dict]
    program_context: list[dict]
    graph_context: str
    structured_context: str
    plan_context: str
    response: str
    sources: list[dict]
