"""Curriculum planner workflow orchestrator — LangGraph + Claude Agent SDK."""

from __future__ import annotations

import uuid

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from backend.lib.orchestrator import WorkflowOrchestrator
from backend.lib.registry import registry, WorkflowConfig
from backend.workflows.planner.state import PlannerState
from backend.workflows.planner.nodes import gather_context_node, plan_agent_node


class PlannerOrchestrator(WorkflowOrchestrator):
    def build_graph(self) -> CompiledStateGraph:
        graph = StateGraph(PlannerState)  # type: ignore[arg-type]

        graph.add_node("gather_context", gather_context_node)
        graph.add_node("plan_agent", plan_agent_node)

        graph.set_entry_point("gather_context")
        graph.add_edge("gather_context", "plan_agent")
        graph.add_edge("plan_agent", END)

        return graph.compile()

    def build_initial_state(
        self,
        student_interests=None,
        program_slug="",
        completed_codes=None,
        target_semesters=4,
        pdf_bytes=None,
        pdf_filename="",
        **kwargs,
    ) -> PlannerState:
        return PlannerState(
            run_id=str(uuid.uuid4()),
            errors=[],
            status="pending",
            student_interests=student_interests or [],
            program_slug=program_slug,
            completed_codes=completed_codes or [],
            target_semesters=target_semesters,
            pdf_bytes=pdf_bytes,  # type: ignore[typeddict-item]
            pdf_filename=pdf_filename,
            guide_pages=[],
            program_requirements={},
            candidate_courses=[],
            work_dir="",
            plan_markdown="",
            plan_semesters=[],
            agent_messages=[],
        )


registry.register(
    WorkflowConfig(
        name="planner",
        orchestrator_class=PlannerOrchestrator,
        description="Multi-semester curriculum planner using Claude Agent SDK + VLM",
    )
)
