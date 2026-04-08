"""Benchmark: Rust vs rapidfuzz vs pure Python Jaro-Winkler on course name data."""

from __future__ import annotations

import random
import time

from rapidfuzz.distance import JaroWinkler

RUST_AVAILABLE = False
try:
    from backend._core import jaro_winkler as rs_jaro_winkler

    RUST_AVAILABLE = True
except ImportError:
    pass


def rf_jaro_winkler(s1: str, s2: str, prefix_weight: float = 0.1) -> float:
    return JaroWinkler.similarity(s1, s2, prefix_weight=prefix_weight)


def py_jaro_winkler(s1: str, s2: str, prefix_weight: float = 0.1) -> float:
    """Pure-Python Jaro-Winkler similarity, used as the baseline for benchmarking.

    Computes similarity in two phases. The **Jaro phase** finds characters that
    match within a sliding window of `floor(max(len(s1), len(s2)) / 2) - 1`
    positions, then counts how many matched pairs appear out of order
    (transpositions). The **Winkler phase** boosts the score when the first 1-4
    characters of both strings agree.

    This is a faithful O(n*m) implementation with no algorithmic tricks — the
    same logic the Rust bitparallel version replaces. Kept here so the benchmark
    measures the cost of Python's per-object overhead on identical logic.
    """
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    len1, len2 = len(s1), len(s2)
    match_window = max(len1, len2) // 2 - 1
    if match_window < 0:
        match_window = 0

    s1_matched = [False] * len1
    s2_matched = [False] * len2
    match_count = 0

    # Matching pass: for each character in s1, search for the first unmatched
    # occurrence of the same character in s2 within the match window.
    for i, ch in enumerate(s1):
        window_start = max(0, i - match_window)
        window_end = min(len2, i + match_window + 1)
        for j in range(window_start, window_end):
            if s2_matched[j] or ch != s2[j]:
                continue
            s1_matched[i] = True
            s2_matched[j] = True
            match_count += 1
            break

    if match_count == 0:
        return 0.0

    # Transposition pass: walk matched characters in order and count pairs
    # where the characters differ (appear in a different sequence).
    transpositions = 0
    s2_cursor = 0
    for i in range(len1):
        if not s1_matched[i]:
            continue
        while not s2_matched[s2_cursor]:
            s2_cursor += 1
        if s1[i] != s2[s2_cursor]:
            transpositions += 1
        s2_cursor += 1

    m = match_count
    jaro = (m / len1 + m / len2 + (m - transpositions // 2) / m) / 3

    # Winkler prefix bonus: up to 4 matching leading characters.
    common_prefix = 0
    for i in range(min(4, len1, len2)):
        if s1[i] == s2[i]:
            common_prefix += 1
        else:
            break

    return jaro + common_prefix * prefix_weight * (1 - jaro)


COURSE_NAMES = [
    "Introduction to Organic Chemistry",
    "Intro Organic Chem",
    "Advanced Calculus",
    "Calculus 1",
    "Principles of Microeconomics",
    "Micro Economics",
    "Introduction to Computer Science",
    "Intro Comp Sci",
    "Linear Algebra and Geometry",
    "Linear Algebra",
    "Fundamentals of Software Engineering",
    "Software Engineering Fundamentals",
    "Molecular Biology of the Cell",
    "Molecular Cell Biology",
    "Introduction to Statistical Learning",
    "Statistical Learning",
    "Thermodynamics and Heat Transfer",
    "Heat Transfer",
    "Applied Machine Learning",
    "Machine Learning Applications",
    "Principles of Financial Accounting",
    "Financial Accounting",
    "Environmental Science and Sustainability",
    "Environmental Sustainability",
    "Introduction to Linguistics",
    "Intro Linguistics",
    "Quantum Mechanics I",
    "Quantum Physics",
    "Neuroanatomy and Neurophysiology",
    "Neuroanatomy",
    "Food Science and Technology",
    "Food Technology",
    "International Development Studies",
    "Intl Development",
    "Oral Health Sciences",
    "Oral Health",
    "Bioresource Engineering Design",
    "Bioresource Design",
    "Atmospheric and Oceanic Sciences",
    "Atmospheric Sciences",
]


def make_pairs(n: int) -> list[tuple[str, str]]:
    random.seed(42)
    pairs = []
    for _ in range(n):
        a = random.choice(COURSE_NAMES)
        b = random.choice(COURSE_NAMES)
        pairs.append((a, b))
    return pairs


def bench_fn(fn, pairs: list[tuple[str, str]], iterations: int) -> float:
    for _ in range(3):
        for a, b in pairs:
            fn(a, b, 0.1)

    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        for a, b in pairs:
            fn(a, b, 0.1)
        times.append(time.perf_counter() - start)
    return sorted(times)[len(times) // 2]


def main() -> None:
    n_pairs = 10_000
    iterations = 100
    pairs = make_pairs(n_pairs)

    print(
        f"\nJaro-Winkler Benchmark: {n_pairs:,} string pairs, median of {iterations} iterations\n"
    )
    print(f"{'Implementation':<20} {'Time':>10} {'vs Python':>10} {'vs rapidfuzz':>13}")
    print("-" * 55)

    py_time = bench_fn(py_jaro_winkler, pairs, iterations)
    print(f"{'Python':<20} {py_time * 1000:>8.1f}ms {'':>10} {'':>13}")

    rf_time = bench_fn(rf_jaro_winkler, pairs, iterations)
    rf_vs_py = py_time / rf_time
    print(
        f"{'rapidfuzz (C++)':<20} {rf_time * 1000:>8.1f}ms {rf_vs_py:>9.1f}x {'':>13}"
    )

    if RUST_AVAILABLE:
        rs_time = bench_fn(rs_jaro_winkler, pairs, iterations)
        rs_vs_py = py_time / rs_time
        rs_vs_rf = rf_time / rs_time
        print(
            f"{'Rust (PyO3)':<20} {rs_time * 1000:>8.1f}ms"
            f" {rs_vs_py:>9.1f}x {rs_vs_rf:>12.1f}x"
        )
    else:
        print("\n  Rust extension not available -- run `make rust-build` first")

    print()


if __name__ == "__main__":
    main()
