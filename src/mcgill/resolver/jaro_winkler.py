"""Jaro-Winkler entity resolution using rapidfuzz."""

from __future__ import annotations

from rapidfuzz.distance import JaroWinkler

from mcgill.models.graph import EntityResolution
from mcgill.resolver.normalize import normalize_name

DEFAULT_THRESHOLD = 0.75


def jaro_winkler_similarity(a: str, b: str) -> float:
    return JaroWinkler.similarity(a, b)


def resolve_name(
    query: str,
    candidates: dict[str, str],
    threshold: float = DEFAULT_THRESHOLD,
) -> EntityResolution:
    """Resolve a query string to the best matching course code.

    Args:
        query: The name to resolve (e.g., "Intro Organic Chem").
        candidates: Mapping of course_code → canonical_title.
        threshold: Minimum similarity score.

    Returns:
        EntityResolution with the best match or None if below threshold.
    """
    norm_query = normalize_name(query)
    best_score = 0.0
    best_code = None
    best_title = None

    for code, title in candidates.items():
        score = jaro_winkler_similarity(norm_query, normalize_name(title))
        if score > best_score:
            best_score = score
            best_code = code
            best_title = title

    if best_score >= threshold:
        return EntityResolution(
            query=query,
            matched_code=best_code,
            matched_title=best_title,
            score=best_score,
            method="jaro_winkler",
        )

    return EntityResolution(query=query, score=best_score)


def batch_resolve(
    queries: list[str],
    candidates: dict[str, str],
    threshold: float = DEFAULT_THRESHOLD,
) -> list[EntityResolution]:
    return [resolve_name(q, candidates, threshold) for q in queries]
