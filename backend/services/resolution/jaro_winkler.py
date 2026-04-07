from __future__ import annotations

from backend.accel import jaro_winkler as jaro_winkler_similarity
from backend.models.graph import EntityResolution
from backend.services.resolution.normalize import normalize_name

DEFAULT_THRESHOLD = 0.75


def resolve_name(
    query: str,
    candidates: dict[str, str],
    threshold: float = DEFAULT_THRESHOLD,
) -> EntityResolution:
    """Resolve a query string to the best matching course code.

    Compares **query** (e.g. `"Intro Organic Chem"`) against every entry in
    **candidates** (a `course_code -> canonical_title` mapping) using Jaro-Winkler
    similarity. Returns an `EntityResolution` with the best match, or `None` fields
    if the best score falls below **threshold**.
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
