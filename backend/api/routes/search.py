"""Search endpoint with hybrid retrieval."""

from __future__ import annotations

from fastapi import APIRouter, Query

router = APIRouter(tags=["Search"])


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1),
    mode: str = Query(default="keyword", pattern="^(keyword|semantic|hybrid)$"),
    top_k: int = Query(default=10, le=50),
):
    if mode == "keyword":
        from backend.services.embedding.retrieval import keyword_search

        results = await keyword_search(q, top_k=top_k)
    elif mode == "semantic":
        from backend.services.embedding.retrieval import semantic_search

        results = await semantic_search(q, top_k=top_k)
    else:
        from backend.services.embedding.retrieval import hybrid_search

        results = await hybrid_search(q, top_k=top_k)

    return {"query": q, "mode": mode, "results": results}
