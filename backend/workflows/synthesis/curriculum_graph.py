"""Curriculum assembly workflow orchestrator."""

from __future__ import annotations

import uuid

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from backend.lib.orchestrator import WorkflowOrchestrator
from backend.lib.registry import registry, WorkflowConfig
from backend.workflows.synthesis.curriculum_state import CurriculumState
from backend.workflows.synthesis.curriculum_nodes import (
    interest_map_node,
    requirements_node,
    candidate_retrieval_node,
    prereq_filter_node,
    conflict_node,
    rank_node,
    assemble_node,
)


class CurriculumOrchestrator(WorkflowOrchestrator):
    def build_graph(self) -> CompiledStateGraph:
        graph = StateGraph(CurriculumState)

        graph.add_node("interest_map", interest_map_node)
        graph.add_node("requirements", requirements_node)
        graph.add_node("candidate_retrieval", candidate_retrieval_node)
        graph.add_node("prereq_filter", prereq_filter_node)
        graph.add_node("conflict", conflict_node)
        graph.add_node("rank", rank_node)
        graph.add_node("assemble", assemble_node)

        graph.set_entry_point("interest_map")
        graph.add_edge("interest_map", "requirements")
        graph.add_edge("requirements", "candidate_retrieval")
        graph.add_edge("candidate_retrieval", "prereq_filter")
        graph.add_edge("prereq_filter", "conflict")
        graph.add_edge("conflict", "rank")
        graph.add_edge("rank", "assemble")
        graph.add_edge("assemble", END)

        return graph.compile()

    def build_initial_state(
        self,
        student_interests=None,
        program_slug="",
        completed_codes=None,
        **kwargs,
    ) -> CurriculumState:
        return CurriculumState(
            run_id=str(uuid.uuid4()),
            errors=[],
            status="pending",
            student_interests=student_interests or [],
            program_slug=program_slug,
            completed_codes=completed_codes or [],
            domain_tags=[],
            program_requirements={},
            candidate_courses=[],
            ranked_courses=[],
            conflicts=[],
            recommendation="",
        )


registry.register(
    WorkflowConfig(
        name="curriculum",
        orchestrator_class=CurriculumOrchestrator,
        description="Curriculum assembly and course recommendation",
    )
)
