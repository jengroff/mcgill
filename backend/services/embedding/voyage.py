"""Voyage AI embedding client."""

from __future__ import annotations

import voyageai

from backend.config import settings

_client: voyageai.Client | None = None

MODEL = "voyage-3"
BATCH_SIZE = 128


def get_client() -> voyageai.Client:
    global _client
    if _client is None:
        _client = voyageai.Client(api_key=settings.voyage_api_key)
    return _client


def embed_texts(texts: list[str], input_type: str = "document") -> list[list[float]]:
    """Embed a list of texts using Voyage AI.

    Args:
        texts: Texts to embed.
        input_type: "document" for indexing, "query" for search queries.

    Returns:
        List of embedding vectors (1024d for voyage-3).
    """
    client = get_client()
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        result = client.embed(batch, model=MODEL, input_type=input_type)
        all_embeddings.extend(result.embeddings)

    return all_embeddings


def embed_query(text: str) -> list[float]:
    """Embed a single search query."""
    return embed_texts([text], input_type="query")[0]
