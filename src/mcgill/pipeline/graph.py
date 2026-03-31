"""LangGraph StateGraph definition for the ingest pipeline."""

from __future__ import annotations

from langgraph.graph import StateGraph, END

from mcgill.pipeline.state import PipelineState
from mcgill.pipeline.nodes import scrape_node, resolve_node, embed_node


def should_continue_after_scrape(state: PipelineState) -> str:
    if state.get("scrape_status") == "error":
        return END
    return "resolve"


def should_continue_after_resolve(state: PipelineState) -> str:
    if state.get("resolve_status") == "error":
        return END
    return "embed"


def should_continue_after_embed(state: PipelineState) -> str:
    return END


def build_pipeline() -> StateGraph:
    graph = StateGraph(PipelineState)

    graph.add_node("scrape", scrape_node)
    graph.add_node("resolve", resolve_node)
    graph.add_node("embed", embed_node)

    graph.set_entry_point("scrape")

    graph.add_conditional_edges("scrape", should_continue_after_scrape)
    graph.add_conditional_edges("resolve", should_continue_after_resolve)
    graph.add_conditional_edges("embed", should_continue_after_embed)

    return graph


def compile_pipeline():
    """Compile the pipeline graph, ready to invoke."""
    graph = build_pipeline()
    return graph.compile()


async def run_pipeline(
    faculty_filter: list[str] | None = None,
    dept_filter: list[str] | None = None,
    max_course_pages: int | None = None,
    max_program_pages: int | None = None,
) -> PipelineState:
    """Run the full ingest pipeline end-to-end."""
    from mcgill.db.postgres import init_db, close_db
    from mcgill.db.neo4j import init_neo4j, close_neo4j

    await init_db()
    await init_neo4j()

    app = compile_pipeline()
    initial_state: PipelineState = {
        "faculty_filter": faculty_filter,
        "dept_filter": dept_filter,
        "max_course_pages": max_course_pages,
        "max_program_pages": max_program_pages,
        "errors": [],
    }

    result = await app.ainvoke(initial_state)

    await close_db()
    await close_neo4j()

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
