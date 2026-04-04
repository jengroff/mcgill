"""Retrieval workflow orchestrator — parallel fan-out retrieval with RRF fusion."""

from __future__ import annotations

import asyncio
import uuid

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from backend.lib.orchestrator import WorkflowOrchestrator
from backend.lib.registry import registry, WorkflowConfig
from backend.workflows.retrieval.state import RetrievalState
from backend.workflows.retrieval.nodes import (
    keyword_node,
    semantic_node,
    graph_node,
    structured_node,
    fusion_node,
)


async def parallel_retrieval_node(state: RetrievalState) -> RetrievalState:
    """Run keyword, semantic, graph, and structured retrieval in parallel."""
    results = await asyncio.gather(
        keyword_node(state),
        semantic_node(state),
        graph_node(state),
        structured_node(state),
        return_exceptions=True,
    )

    merged: dict = {}
    errors: list[str] = []
    for r in results:
        if isinstance(r, Exception):
            errors.append(str(r))
        elif isinstance(r, dict):
            errors.extend(r.pop("errors", []))
            merged.update(r)

    if errors:
        merged["errors"] = errors
    return merged


class RetrievalOrchestrator(WorkflowOrchestrator):
    def build_graph(self) -> CompiledStateGraph:
        graph = StateGraph(RetrievalState)

        graph.add_node("retrieve", parallel_retrieval_node)
        graph.add_node("fusion", fusion_node)

        graph.set_entry_point("retrieve")
        graph.add_edge("retrieve", "fusion")
        graph.add_edge("fusion", END)

        return graph.compile()

    def build_initial_state(
        self, query="", top_k=10, mode="hybrid", **kwargs
    ) -> RetrievalState:
        return RetrievalState(
            run_id=str(uuid.uuid4()),
            errors=[],
            status="pending",
            query=query,
            top_k=top_k,
            mode=mode,
            keyword_results=[],
            semantic_results=[],
            program_results=[],
            graph_context="",
            structured_context="",
            fused_results=[],
        )


registry.register(
    WorkflowConfig(
        name="retrieval",
        orchestrator_class=RetrievalOrchestrator,
        description="Hybrid dense + sparse retrieval with RRF fusion",
    )
)
