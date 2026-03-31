"""Hybrid retrieval combining semantic search (pgvector) and keyword search (full-text)."""

from __future__ import annotations

from mcgill.db.postgres import get_pool
from mcgill.embeddings.voyage import embed_query
from mcgill.embeddings.vector_store import search_similar, search_similar_programs


async def keyword_search(query: str, top_k: int = 10) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT code, title, description, dept, faculty,
                      ts_rank(tsv, websearch_to_tsquery('english', $1)) AS rank
               FROM courses
               WHERE tsv @@ websearch_to_tsquery('english', $1)
               ORDER BY rank DESC
               LIMIT $2""",
            query, top_k,
        )
        return [dict(r) for r in rows]


async def semantic_search(query: str, top_k: int = 10) -> list[dict]:
    query_emb = embed_query(query)
    return await search_similar(query_emb, top_k)


async def program_search(query: str, top_k: int = 5) -> list[dict]:
    """Semantic search over program guide pages."""
    query_emb = embed_query(query)
    return await search_similar_programs(query_emb, top_k)


def reciprocal_rank_fusion(
    *result_lists: list[dict],
    k: int = 60,
    top_n: int = 10,
    id_key: str = "code",
) -> list[dict]:
    """Merge multiple ranked lists using Reciprocal Rank Fusion (RRF).

    Score = sum(1 / (k + rank)) across all lists for each item.
    """
    scores: dict[str, float] = {}
    items: dict[str, dict] = {}

    for results in result_lists:
        for rank, item in enumerate(results):
            item_id = item.get(id_key, str(rank))
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank + 1)
            if item_id not in items:
                items[item_id] = item

    sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)[:top_n]
    return [
        {**items[id_], "rrf_score": scores[id_]}
        for id_ in sorted_ids
        if id_ in items
    ]


async def hybrid_search(query: str, top_k: int = 10) -> list[dict]:
    """Run both semantic and keyword search, fuse with RRF."""
    kw_results = await keyword_search(query, top_k=top_k * 2)
    sem_results = await semantic_search(query, top_k=top_k * 2)

    # Normalize semantic results to have a 'code' key for fusion
    for r in sem_results:
        if "code" not in r:
            r["code"] = r.get("code", "")

    return reciprocal_rank_fusion(kw_results, sem_results, top_n=top_k)
