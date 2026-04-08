from __future__ import annotations

import uuid

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from backend.services.lib.orchestrator import WorkflowOrchestrator
from backend.services.lib.registry import registry, WorkflowConfig
from backend.workflows.synthesis.state import SynthesisState
from backend.workflows.synthesis.nodes import context_pack_node, synthesize_node


class SynthesisOrchestrator(WorkflowOrchestrator):
    def build_graph(self) -> CompiledStateGraph:
        graph = StateGraph(SynthesisState)  # type: ignore[arg-type]

        graph.add_node("context_pack", context_pack_node)
        graph.add_node("synthesize", synthesize_node)

        graph.set_entry_point("context_pack")
        graph.add_edge("context_pack", "synthesize")
        graph.add_edge("synthesize", END)

        return graph.compile()

    def build_initial_state(
        self,
        query="",
        session_id="",
        conversation_history=None,
        retrieval_context=None,
        program_context=None,
        graph_context="",
        structured_context="",
        plan_context="",
        **kwargs,
    ) -> SynthesisState:
        return SynthesisState(
            run_id=str(uuid.uuid4()),
            errors=[],
            status="pending",
            query=query,
            session_id=session_id,
            conversation_history=conversation_history or [],
            retrieval_context=retrieval_context or [],
            program_context=program_context or [],
            graph_context=graph_context,
            structured_context=structured_context,
            plan_context=plan_context,
            response="",
            sources=[],
        )


registry.register(
    WorkflowConfig(
        name="synthesis",
        orchestrator_class=SynthesisOrchestrator,
        description="Curriculum assembly and advisor synthesis",
    )
)
