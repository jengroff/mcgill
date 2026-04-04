"""Ingestion workflow orchestrator — extract -> chunk -> embed -> store."""

from __future__ import annotations

import uuid

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from backend.lib.orchestrator import WorkflowOrchestrator
from backend.lib.registry import registry, WorkflowConfig
from backend.workflows.ingestion.state import IngestionState
from backend.workflows.ingestion.nodes import (
    extract_node,
    chunk_node,
    embed_node,
    store_node,
)


class IngestionOrchestrator(WorkflowOrchestrator):
    def build_graph(self) -> CompiledStateGraph:
        graph = StateGraph(IngestionState)

        graph.add_node("extract", extract_node)
        graph.add_node("chunk", chunk_node)
        graph.add_node("embed", embed_node)
        graph.add_node("store", store_node)

        graph.set_entry_point("extract")
        graph.add_edge("extract", "chunk")
        graph.add_edge("chunk", "embed")
        graph.add_edge("embed", "store")
        graph.add_edge("store", END)

        return graph.compile()

    def build_initial_state(
        self,
        source_type="pdf",
        source_path="",
        source_bytes=b"",
        faculty_slug="",
        **kwargs,
    ) -> IngestionState:
        return IngestionState(
            run_id=str(uuid.uuid4()),
            errors=[],
            status="pending",
            source_type=source_type,
            source_path=source_path,
            source_bytes=source_bytes,
            faculty_slug=faculty_slug,
            raw_text="",
            structured_sections=[],
            chunks=[],
            embeddings=[],
            chunks_stored=0,
        )


registry.register(
    WorkflowConfig(
        name="ingestion",
        orchestrator_class=IngestionOrchestrator,
        description="PDF / URL ingestion -> chunk -> embed",
    )
)
