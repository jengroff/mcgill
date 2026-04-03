"""Retrieval workflow orchestrator — parallel fan-out retrieval with RRF fusion."""

from __future__ import annotations

import uuid

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from backend.lib.orchestrator import WorkflowOrchestrator
from backend.lib.registry import registry, WorkflowConfig
from backend.workflows.retrieval.state import RetrievalState
from backend.workflows.retrieval.nodes import (
    keyword_node,
    semantic_node,
    program_node,
    graph_node,
    structured_node,
    fusion_node,
)


def _after_retrieval(state: RetrievalState) -> str:
    """All retrieval nodes route to fusion."""
    return "fusion"


class RetrievalOrchestrator(WorkflowOrchestrator):
    def build_graph(self) -> CompiledStateGraph:
        graph = StateGraph(RetrievalState)

        # Parallel retrieval nodes
        graph.add_node("keyword", keyword_node)
        graph.add_node("semantic", semantic_node)
        graph.add_node("program", program_node)
        graph.add_node("graph", graph_node)
        graph.add_node("structured", structured_node)
        graph.add_node("fusion", fusion_node)

        graph.set_entry_point("keyword")
        graph.add_edge("keyword", "semantic")
        graph.add_edge("semantic", "program")
        graph.add_edge("program", "graph")
        graph.add_edge("graph", "structured")
        graph.add_edge("structured", "fusion")
        graph.add_edge("fusion", END)

        return graph.compile()

    def build_initial_state(self, query="", top_k=10, mode="hybrid", **kwargs) -> RetrievalState:
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


registry.register(WorkflowConfig(
    name="retrieval",
    orchestrator_class=RetrievalOrchestrator,
    description="Hybrid dense + sparse retrieval with RRF fusion",
))
