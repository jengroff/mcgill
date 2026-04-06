from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from backend._core import jaro_winkler as _rs_jaro_winkler

    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False
    logger.info("Rust extension not available — using pure Python fallback")


def jaro_winkler(s1: str, s2: str, prefix_weight: float = 0.1) -> float:
    """Jaro-Winkler similarity between two strings (0.0 to 1.0).

    Uses the Rust PyO3 extension when compiled, otherwise falls back
    to a pure-Python implementation of the same algorithm.
    """
    if RUST_AVAILABLE:
        return float(_rs_jaro_winkler(s1, s2, prefix_weight))

    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    max_dist = max(len(s1), len(s2)) // 2 - 1
    if max_dist < 0:
        max_dist = 0
    s1_matches = [False] * len(s1)
    s2_matches = [False] * len(s2)
    matches = 0
    transpositions = 0
    for i, c1 in enumerate(s1):
        start = max(0, i - max_dist)
        end = min(len(s2), i + max_dist + 1)
        for j in range(start, end):
            if s2_matches[j] or c1 != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break
    if matches == 0:
        return 0.0
    k = 0
    for i, c1 in enumerate(s1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if c1 != s2[k]:
            transpositions += 1
        k += 1
    jaro = (
        matches / len(s1) + matches / len(s2) + (matches - transpositions / 2) / matches
    ) / 3
    prefix = 0
    for i in range(min(4, min(len(s1), len(s2)))):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break
    return jaro + prefix * prefix_weight * (1 - jaro)
