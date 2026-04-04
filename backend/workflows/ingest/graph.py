from __future__ import annotations

import uuid

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from backend.lib.orchestrator import WorkflowOrchestrator
from backend.lib.registry import registry, WorkflowConfig
from backend.workflows.ingest.state import IngestState
from backend.workflows.ingest.nodes import precheck_node, scrape_node, resolve_node, embed_node


def _after_precheck(state: IngestState) -> str:
    if state.get("scrape_status") == "error":
        return END
    if not state.get("active_depts"):
        return END
    return "scrape"


def _after_scrape(state: IngestState) -> str:
    if state.get("scrape_status") == "error":
        return END
    return "resolve"


def _after_resolve(state: IngestState) -> str:
    if state.get("resolve_status") == "error":
        return END
    return "embed"


def _after_embed(state: IngestState) -> str:
    return END


class IngestOrchestrator(WorkflowOrchestrator):
    def build_graph(self) -> CompiledStateGraph:
        graph = StateGraph(IngestState)

        graph.add_node("precheck", precheck_node)
        graph.add_node("scrape", scrape_node)
        graph.add_node("resolve", resolve_node)
        graph.add_node("embed", embed_node)

        graph.set_entry_point("precheck")

        graph.add_conditional_edges("precheck", _after_precheck)
        graph.add_conditional_edges("scrape", _after_scrape)
        graph.add_conditional_edges("resolve", _after_resolve)
        graph.add_conditional_edges("embed", _after_embed)

        return graph.compile()

    def build_initial_state(
        self,
        faculty_filter=None,
        dept_filter=None,
        max_course_pages=None,
        max_program_pages=None,
        force=False,
        **kwargs,
    ) -> IngestState:
        return IngestState(
            run_id=str(uuid.uuid4()),
            errors=[],
            status="pending",
            faculty_filter=faculty_filter,
            dept_filter=dept_filter,
            max_course_pages=max_course_pages,
            max_program_pages=max_program_pages,
            force=force,
        )


registry.register(WorkflowConfig(
    name="ingest",
    orchestrator_class=IngestOrchestrator,
    description="Scrape -> resolve -> chunk -> embed",
))


async def run_pipeline(
    faculty_filter: list[str] | None = None,
    dept_filter: list[str] | None = None,
    max_course_pages: int | None = None,
    max_program_pages: int | None = None,
    force: bool = False,
) -> IngestState:
    """Run the full ingest pipeline end-to-end (CLI entry point)."""
    from backend.db.postgres import init_db, close_db
    from backend.db.neo4j import init_neo4j, close_neo4j

    await init_db()
    await init_neo4j()

    orchestrator = IngestOrchestrator()
    result = await orchestrator.run(
        faculty_filter=faculty_filter,
        dept_filter=dept_filter,
        max_course_pages=max_course_pages,
        max_program_pages=max_program_pages,
        force=force,
    )

    await close_db()
    await close_neo4j()

    skipped = result.get("skipped_depts", [])
    if skipped:
        print(f"\nSkipped {len(skipped)} already-processed departments: {', '.join(sorted(skipped))}")
    if not result.get("active_depts"):
        print("All departments already processed. Use --force to re-run.")
        return result

    print(f"\nPipeline complete:")
    print(f"  Courses scraped:  {result.get('courses_scraped', 0)}")
    print(f"  Entities created: {result.get('entities_created', 0)}")
    print(f"  Relationships:    {result.get('relationships_created', 0)}")
    print(f"  Chunks embedded:  {result.get('chunks_created', 0)}")
    if result.get("errors"):
        print(f"  Errors: {len(result['errors'])}")
        for e in result["errors"]:
            print(f"    - {e[:200]}")

    return result
