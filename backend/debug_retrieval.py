import asyncio

from backend.db.postgres import init_db
from backend.workflows.retrieval.graph import RetrievalOrchestrator
from backend.workflows.synthesis.nodes import context_pack_node


async def test():
    await init_db()
    orch = RetrievalOrchestrator()
    state = await orch.run(
        query="what are the key dates in fall 2026", top_k=10, mode="hybrid"
    )

    print("=== PROGRAM RESULTS ===")
    for r in state.get("program_results", [])[:5]:
        sim = r.get("similarity", 0)
        cid = r.get("id")
        pid = r.get("program_page_id")
        title = r.get("title", "")
        text = r.get("text", "")[:100]
        print(f"  sim={sim:.3f} chunk={cid} page={pid} title={title!r}")
        print(f"    {text}")

    print()
    print("=== STRUCTURED CONTEXT ===")
    ctx = state.get("structured_context", "")
    print(ctx[:200] if ctx else "(empty)")

    print()
    pack = await context_pack_node(
        {
            "query": "what are the key dates in fall 2026",
            "retrieval_context": state.get("fused_results", []),
            "program_context": state.get("program_results", []),
            "graph_context": state.get("graph_context", ""),
            "structured_context": state.get("structured_context", ""),
        }
    )
    ctx = pack["sources"][0]["context_text"]
    for key in [
        "Classes begin",
        "Reading Break",
        "Exams begin",
        "Labour Day",
        "Thanksgiving",
    ]:
        print(f"{key}: {'PASS' if key in ctx else 'FAIL'}")
    print(f"Context length: {len(ctx)} chars")


asyncio.run(test())
