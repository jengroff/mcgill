"""Retrieval workflow nodes — keyword, semantic, program, graph, fusion."""

from __future__ import annotations

import re
import traceback

from backend.workflows.retrieval.state import RetrievalState


async def keyword_node(state: RetrievalState) -> RetrievalState:
    """Full-text keyword search on courses."""
    try:
        from backend.services.embedding.retrieval import keyword_search
        results = await keyword_search(state["query"], top_k=state.get("top_k", 10))
        return {"keyword_results": results}
    except Exception as e:
        return {"keyword_results": [], "errors": [f"keyword: {e}\n{traceback.format_exc()}"]}


async def semantic_node(state: RetrievalState) -> RetrievalState:
    """Dense vector semantic search on course chunks."""
    try:
        from backend.services.embedding.retrieval import semantic_search
        results = await semantic_search(state["query"], top_k=state.get("top_k", 10))
        return {"semantic_results": results}
    except Exception as e:
        return {"semantic_results": [], "errors": [f"semantic: {e}\n{traceback.format_exc()}"]}


async def program_node(state: RetrievalState) -> RetrievalState:
    """Semantic search on program guide pages."""
    try:
        from backend.services.embedding.retrieval import program_search
        results = await program_search(state["query"], top_k=5)
        return {"program_results": results}
    except Exception as e:
        return {"program_results": [], "errors": [f"program: {e}\n{traceback.format_exc()}"]}


async def graph_node(state: RetrievalState) -> RetrievalState:
    """Neo4j prerequisite query if course codes detected in query."""
    try:
        codes = re.findall(r"\b([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)\b", state["query"].upper())
        if not codes:
            return {"graph_context": ""}

        from backend.db.neo4j import run_query
        code = f"{codes[0][0]} {codes[0][1]}"
        prereqs = await run_query(
            """MATCH (c:Course {code: $code})-[:PREREQUISITE_OF]->(p:Course)
               RETURN p.code AS code, p.title AS title""",
            {"code": code},
        )
        if prereqs:
            ctx = f"Prerequisites for {code}: " + ", ".join(
                f"{r['code']} ({r['title']})" for r in prereqs
            )
            return {"graph_context": ctx}
        return {"graph_context": ""}
    except Exception as e:
        return {"graph_context": "", "errors": [f"graph: {e}\n{traceback.format_exc()}"]}


async def fusion_node(state: RetrievalState) -> RetrievalState:
    """Reciprocal rank fusion across keyword + semantic results."""
    try:
        from backend.services.embedding.retrieval import reciprocal_rank_fusion
        fused = reciprocal_rank_fusion(
            state.get("keyword_results", []),
            state.get("semantic_results", []),
            top_n=state.get("top_k", 10),
        )
        return {"fused_results": fused, "status": "complete"}
    except Exception as e:
        # Fall back to whatever results we have
        fallback = state.get("keyword_results", []) or state.get("semantic_results", [])
        return {"fused_results": fallback, "status": "complete", "errors": [f"fusion: {e}"]}
