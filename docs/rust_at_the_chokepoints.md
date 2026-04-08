*Joshua Engroff · April 2026*

# Rust at the Chokepoints

*Accelerating CPU-bound work in agentic pipelines*

> **TL;DR:** I dropped a single Rust function into a Python agentic platform via PyO3 and measured a 12.8x speedup on the CPU-bound stage that sits between LLM calls. This post walks through the benchmark, deep-dives into why Jaro-Winkler string similarity runs 12.8x faster in Rust, and argues that selective Rust acceleration is the highest-leverage performance move for agent builders today.

## 1. The Problem: Agents Aren't Just Waiting on LLMs

There's a comfortable assumption in the agentic AI community: since most of the wall-clock time is spent waiting on LLM API calls, the speed of the orchestration language doesn't matter. Python is fine. It's glue code. The model is the bottleneck.

This is true right up until you're fuzzy-matching a user query against 4,900 course names.

Between every LLM call in a production agent pipeline sits CPU-bound orchestration work. The agent resolves entities by fuzzy-matching names across large record sets. It normalizes and compares strings across thousands of candidates before the model ever sees them. These stages run synchronously on the critical path, and when they take hundreds of milliseconds, they serialize the agent's entire decision loop.

The problem compounds with scale. Fuzzy-match 10,000 string pairs in pure Python and you're waiting 192 milliseconds per batch — which adds up fast when you're resolving course names, prerequisite references, and advisor lookups across an entire university catalog.

At these workloads, the orchestration layer, not the LLM, becomes the bottleneck.

I encountered this firsthand building a Claude-powered course advisor for McGill University. The platform scrapes, resolves, embeds, and serves ~4,900 courses across 12 faculties via a LangGraph agent with a React frontend. Entity resolution (matching fuzzy user inputs like "Intro Organic Chem" to the canonical "CHEM 212: Introduction to Organic Chemistry 1") sits on the critical path before every retrieval call.

So I decided to see what Rust could do about it.

## 2. The Approach: Surgical Rust via PyO3

The strategy was deliberately narrow: don't rewrite the platform, rewrite the inner loop.

I identified one function where Python's per-element overhead dominated runtime, wrote a Rust equivalent using PyO3, and exposed it as a native Python extension module. The total investment: 103 lines of Rust, compiled via `maturin develop --release` in under ten seconds.

The integration layer is a single Python file, `accel.py`, that tries to import the Rust extension and falls back to a pure-Python implementation if it's not available:

```python
try:
    from backend._core import jaro_winkler as _rs_jaro_winkler
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False
```

The calling code never changes. Same function signature. Same test suite. The Rust extension is invisible to every module that consumes it.

What I accelerated:

| Function | Pipeline Stage | What It Does |
| --- | --- | --- |
| `jaro_winkler` | Entity Resolution | Fuzzy string matching for course name resolution |

The entity resolution service calls `jaro_winkler` inside a tight loop over the full course catalog:

```python
for code, title in candidates.items():
    score = jaro_winkler_similarity(norm_query, normalize_name(title))
    if score > best_score:
        best_score = score
        best_code = code
        best_title = title
```

Each query triggers ~4,900 string comparisons. Batch resolution of a dozen queries means tens of thousands of comparisons per request. This is the exact profile where Rust wins: a tight loop over primitive data, run synchronously on the critical path, with no I/O to hide behind.

The key insight: you don't replace Python. You replace the inner loop where Python's per-object overhead dominates: the tight, element-level iteration over bytes and booleans that the language was never designed to run fast.

## 3. The Results: 12.8x

The benchmark was run single-threaded on a release build, Python 3.12 and Rust 1.93, with PyO3 0.28 handling the bridge. The reported speedup *includes* the cost of converting Python data structures into Rust types (Python `str` to Rust `&str`). The pure compute advantage is higher.

| | Time | Speedup |
| --- | ---: | ---: |
| **Python** | **192.3ms** | |
| **Rust (PyO3)** | **15.1ms** | **12.8x** |

*10,000 string pairs, median of 100 iterations, 3 warmup runs discarded.*

The test data uses realistic course name pairs — "Introduction to Organic Chemistry" vs "Intro Organic Chem", "Advanced Calculus" vs "Calculus 1", "Neuroanatomy and Neurophysiology" vs "Neuroanatomy" — 40 real course name variants sampled into 10,000 random pairings.

In practice, this means resolving a course name against the full 4,900-entry McGill catalog drops from ~94ms to ~7ms per query. A batch of 10 queries goes from nearly a second to about 74 milliseconds, the kind of improvement that turns a noticeable pause into an instant response.

## 4. Deep Dive: Why Jaro-Winkler Runs 12.8x Faster in Rust

Both implementations use the same algorithm. Same data structures. Same loop structure. There is no algorithmic trick in the Rust version — the 12.8x speedup comes entirely from how the two languages execute identical logic.

### The Algorithm

Jaro-Winkler string similarity works in four steps:

1. **Matching pass.** For each character in string `s1`, search for a matching character in `s2` within a distance window. Track matched characters in each string.
2. **Transposition pass.** Walk through matched characters in order. Count pairs appearing in different positions.
3. **Jaro score.** Combine match count and transposition count: `(m/|s1| + m/|s2| + (m - t/2)/m) / 3`.
4. **Winkler prefix bonus.** If the first 1-4 characters match, boost the score proportionally.

Both implementations allocate two boolean arrays, run a nested loop for the matching pass, a single loop for transpositions, and a short loop for the prefix. The structures are identical. The speed is not.

### Side by Side: The Matching Pass

**Python:**

```python
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
```

**Rust:**

```rust
for i in 0..len1 {
    let start = i.saturating_sub(max_dist);
    let end = (i + max_dist + 1).min(len2);
    for j in start..end {
        if s2_matched[j] || s1_bytes[i] != s2_bytes[j] {
            continue;
        }
        s1_matched[i] = true;
        s2_matched[j] = true;
        matches += 1;
        break;
    }
}
```

Read them side by side. The logic is the same. The performance is not, because every line that looks equivalent is doing fundamentally different work under the hood.

### Where the 12.8x Comes From

The speedup is the compound effect of four layers of overhead, all multiplied together inside the nested loop.

#### 1. Per-character object overhead — the dominant factor

When Python evaluates `c1 != s2[j]`, here's what actually happens: `s2[j]` indexes into a Python string object, allocating a new single-character `str` on the heap (28 bytes, reference-counted). `!=` invokes `str.__eq__`, which performs a type check, a length check, and finally a byte comparison. The temporary string object is then decremented and freed.

This happens for *every character comparison in the inner loop*.

In Rust, `s1_bytes[i] != s2_bytes[j]` is a single byte comparison — one CPU instruction, no allocation, no dispatch. At roughly 100 nanoseconds of Python overhead per comparison versus roughly 1 nanosecond in Rust, this single factor accounts for most of the gap.

#### 2. Boolean array overhead

Python's `s1_matches = [False] * len(s1)` creates a list of Python `bool` objects (28 bytes each). Writing `s1_matches[i] = True` means: decrement the reference count on `False`, increment on `True`, store a new pointer. Rust's `vec![false; len1]` allocates a contiguous array of bytes. Writing `s1_matched[i] = true` is a single byte store.

#### 3. Loop and iterator overhead

`for i, c1 in enumerate(s1)` creates an `enumerate` iterator object, calls `__next__` on each iteration, and unpacks a two-element tuple. Rust's `for i in 0..len1` compiles down to a register increment and a comparison — no iterator object, no method dispatch, no tuple allocation.

#### 4. Built-in function call overhead

`max(0, i - max_dist)` performs a global namespace lookup, constructs an argument tuple, and enters the function call protocol. Rust's `i.saturating_sub(max_dist)` compiles to a single CPU instruction.

> *None of these overheads are individually catastrophic. But they stack multiplicatively inside a nested loop that runs millions of iterations.*

### What This Tells You Generally

The Jaro-Winkler case reveals the pattern for when Rust wins biggest over Python: element-level iteration, nested loops, simple data structures where contiguous memory layout matters, and cases where Python's dynamic dispatch has no work to do — every element is the same type, every operation is the same. Python pays for dynamism it doesn't use.

This is exactly the profile of most orchestration-layer compute in agentic workflows: fuzzy matching, embedding similarity, numerical projection.

## 5. When (and When Not) to Reach for Rust

Not every slow function justifies a Rust rewrite. Here's the decision framework I use.

**Reach for Rust when:**

- You have a tight loop over primitive data — floats, bytes, integers. Not dicts, not dataclasses, not ORM models.
- The loop exceeds roughly 1 million iterations per call.
- The function sits on the synchronous critical path of the agent.
- You can define a clean, narrow interface. The ideal Rust function takes flat values in and returns flat values out.

**Don't bother when:**

- The bottleneck is I/O. LLM API latency, database roundtrips, and network calls dwarf any CPU savings.
- numpy or scipy already handle the math. They're calling optimized C and Fortran under the hood.
- The function runs under 1ms in pure Python. The PyO3 boundary crossing costs microseconds.
- The logic is inherently about Python objects — building prompts, parsing JSON, traversing ORM relationships.

**The integration cost is lower than you think.** PyO3 and maturin handle the build toolchain. You write normal Rust, run `maturin develop --release`, and import from Python. The pure-Python fallback in `accel.py` means the extension is optional: CI runs without Rust, development machines compile it, production gets the speedup. The same test suite validates both code paths.

For me, 103 lines of Rust in one function was a single afternoon of work. The speedup is permanent.

## 6. Conclusion

The next wave of agentic performance gains isn't in the model. It's in the orchestration layer.

Most agent builders write Python, and Python is the right choice for the glue: prompt construction, tool dispatch, state management, API integration. But between those LLM calls sit CPU-bound stages — entity matching, retrieval scoring, numerical modeling, where Python's per-object overhead converts directly into agent latency.

Selective Rust acceleration targets exactly these chokepoints. Not a rewrite. Not a new architecture. One function, 103 lines of Rust, dropped into the existing Python codebase via PyO3 with a pure-Python fallback for environments that don't compile it.

The result: 12.8x faster on the function that was actually bottlenecking my agent. Course name resolution across a 4,900-entry catalog went from 94ms to 7ms per query.

The bar for "when should I write this in Rust" is lower than most people think. If you have a hot loop over primitive data on your agent's critical path, the answer is probably now.

---

## Appendix

### A. Benchmark Methodology

- **Runtime:** Python 3.12, Rust 1.93, PyO3 0.28
- **Build:** `maturin develop --release` (single-threaded, release optimizations)
- **Measurement:** Median of 100 iterations per workload, 3 warmup runs discarded
- **Overhead included:** All speedup figures include the cost of Python-to-Rust data conversion. Pure compute speedups are higher.
- **Test data:** 40 realistic McGill course name variants (full and abbreviated forms), randomly sampled into 10,000 pairings with a fixed seed for reproducibility.

### Full Results

| Function | Workload | Python | Rust | Speedup |
| --- | --- | ---: | ---: | ---: |
| jaro_winkler | 10k string pairs | 192.3ms | 15.1ms | **12.8x** |

- Jaro-Winkler sees a large win because string iteration in Rust avoids Python's per-character object overhead
- The Rust implementation operates on raw bytes (`s1.as_bytes()`) with contiguous boolean arrays, while Python allocates a 28-byte `str` object for every character comparison
- The function falls back to pure Python gracefully if the Rust extension is not compiled
- Build: `maturin develop --release` — compiles in under 10 seconds

---

*Joshua Engroff · Rust Acceleration Benchmarks · PyO3 0.28 · April 2026*
