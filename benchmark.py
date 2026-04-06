"""Benchmark: Rust vs pure Python Jaro-Winkler on course name data."""

from __future__ import annotations

import random
import time

RUST_AVAILABLE = False
try:
    from backend._core import jaro_winkler as rs_jaro_winkler

    RUST_AVAILABLE = True
except ImportError:
    pass


def py_jaro_winkler(s1: str, s2: str, prefix_weight: float = 0.1) -> float:
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
        f"\nJaro-Winkler Benchmark — {n_pairs:,} string pairs, median of {iterations} iterations\n"
    )
    print(f"{'Implementation':<16} {'Time':>10} {'Speedup':>10}")
    print("-" * 38)

    py_time = bench_fn(py_jaro_winkler, pairs, iterations)
    print(f"{'Python':<16} {py_time * 1000:>8.1f}ms {'—':>10}")

    if RUST_AVAILABLE:
        rs_time = bench_fn(rs_jaro_winkler, pairs, iterations)
        speedup = py_time / rs_time
        print(f"{'Rust (PyO3)':<16} {rs_time * 1000:>8.1f}ms {speedup:>9.1f}x")
    else:
        print("\n  Rust extension not available — run `make rust-build` first")

    print()


if __name__ == "__main__":
    main()
