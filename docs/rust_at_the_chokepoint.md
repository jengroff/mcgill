## Rust at the Chokepoints

*Accelerating CPU-bound work in agentic pipelines*

> **TL;DR:** I dropped a single Rust function into a Python agentic platform via PyO3 and measured a ~107x speedup over pure Python and a ~2x speedup over rapidfuzz, the best C++ string matching library available. This post walks through the benchmark, explains how a bitparallel Jaro-Winkler implementation in Rust outperforms both, and argues that selective Rust acceleration is one of the highest-leverage performance moves available to agent builders.

---

## 1. The Problem: Agents Aren't Just Waiting on LLMs

There is a comfortable assumption in the agentic AI community that most wall clock time is spent waiting on LLM API calls, so the speed of the orchestration layer does not matter. Python is fine. It is glue code. The model is the bottleneck.

That holds right up until you are fuzzy matching a user query against 4,900 course names.

In practice, every LLM call in a production agent pipeline is surrounded by CPU-bound orchestration work. The agent resolves entities by matching user input against large record sets, normalizing and comparing strings across thousands of candidates before the model ever sees them. These stages run synchronously on the critical path, so when they take hundreds of milliseconds they effectively serialize the entire decision loop.

The problem compounds with scale. Fuzzy matching 10,000 string pairs in pure Python takes roughly 172 milliseconds per batch, which adds up quickly when resolving course names, prerequisite references, and advisor lookups across a full catalog.

At these workloads, the orchestration layer becomes the bottleneck rather than the model.

I encountered this firsthand while building a Claude-powered course advisor for McGill University. The platform scrapes, resolves, embeds, and serves roughly 4,900 courses across 12 faculties via a LangGraph agent with a React frontend. Entity resolution, matching inputs like "Intro Organic Chem" to "CHEM 212: Introduction to Organic Chemistry 1," sits directly on the critical path before every retrieval call.

So I decided to see what Rust could do about it.

---

## 2. The Approach: Surgical Rust via PyO3

The strategy was deliberately narrow. Do not rewrite the platform, rewrite the inner loop.

I identified one function where Python's per element overhead dominated runtime, wrote a Rust equivalent using PyO3, and exposed it as a native Python extension module. The total investment was about 140 lines of Rust, compiled via `maturin develop --release` in under ten seconds.

The integration layer is a single Python file, `accel.py`, which attempts to import the Rust extension and falls back to a pure Python implementation if it is not available:

```python
try:
    from backend._core import jaro_winkler as _rs_jaro_winkler
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False
```

The calling code does not change, with the same function signature and the same test suite. The Rust extension is effectively invisible to the rest of the system.

What I accelerated:

| Function       | Pipeline Stage    | What It Does                                     |
| -------------- | ----------------- | ------------------------------------------------ |
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

Each query triggers roughly 4,900 string comparisons. Batch resolution of a dozen queries means tens of thousands of comparisons per request. This is exactly the profile where Rust performs well: a tight loop over primitive data, running synchronously on the critical path, with no I/O to mask the cost.

---

## 3. The Results

The first question any experienced Python developer should ask is: why not use rapidfuzz? It is the standard library for fast string matching in Python, backed by a C++ implementation that uses bitparallel algorithms internally. It is a `pip install` away.

So I benchmarked against it.

|                     |        Time | vs Python | vs rapidfuzz |
| ------------------- | ----------: | --------: | -----------: |
| **Python**          | **171.7ms** |           |              |
| **rapidfuzz (C++)** |   **3.2ms** | **53.7x** |              |
| **Rust (PyO3)**     |   **1.6ms** | **107.3x** |    **2.0x**  |

*10,000 string pairs, median of 100 iterations, 3 warmup runs discarded. Python 3.12, Rust 1.93, PyO3 0.28, rapidfuzz 3.14. Single threaded, release build. Speedups include the cost of Python-to-Rust data conversion. The Rust-vs-rapidfuzz ratio varies from ~1.8x to ~2.2x across runs due to sub-millisecond measurement noise.*

The Rust implementation is roughly 2x faster than rapidfuzz and ~107x faster than pure Python. Both the Rust and rapidfuzz implementations use bitparallel Jaro-Winkler, the same family of algorithm. The difference comes from the implementation: the Rust version is purpose-built for this workload, operating directly on byte slices with no support for Unicode normalization, score cutoffs, or arbitrary-length strings. rapidfuzz is a general-purpose library that handles all of those, and the generality has a cost.

The test data uses realistic course name pairs such as "Introduction to Organic Chemistry" versus "Intro Organic Chem," "Advanced Calculus" versus "Calculus 1," and "Neuroanatomy and Neurophysiology" versus "Neuroanatomy," sampled into 10,000 random pairings.

In practice, resolving a course name against the full 4,900 entry catalog takes under 1 millisecond per query with the Rust implementation, compared to about 1.6 milliseconds with rapidfuzz and 84 milliseconds in pure Python. A batch of 10 queries completes in about 8 milliseconds, which is the difference between a noticeable pause and an instant response.

---

## 4. Deep Dive: Naive to Bitparallel

### Why Naive Rust is Already Fast

My first implementation was a direct port of the Python Jaro-Winkler into Rust: same algorithm, same data structures, same nested loops. That version ran in about 12 milliseconds on the benchmark, roughly a 14x speedup over Python. The improvement came entirely from how the two languages execute identical logic.

The standard Jaro matching pass scans a window of characters for each position in the first string:

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

In Python, every character comparison allocates a temporary string object, every boolean write updates reference counts, and every loop iteration involves method dispatch. In Rust, the same loop compiles down to byte comparisons, byte stores, and register increments. That overhead gap accounts for the 14x difference on identical logic.

But 14x is not the end of the story. rapidfuzz already runs at 54x by using a fundamentally better algorithm. To compete, the Rust implementation needed the same treatment.

### Bitparallel Jaro-Winkler

The bitparallel approach eliminates the inner loop of the matching pass entirely. Instead of scanning the match window character by character, it encodes character positions as bitmasks and resolves each match with a few bitwise operations.

**Preprocessing.** For the shorter string (the pattern), build a lookup table where each byte value maps to a `u64` bitmask with bit `i` set wherever that byte appears:

```rust
let mut pm = [0u64; 256];
for (i, &b) in pattern.iter().enumerate() {
    pm[b as usize] |= 1u64 << i;
}
```

For the pattern `"organic"`, `pm[b'o']` would have bit 0 set, `pm[b'r']` bit 1, `pm[b'g']` bit 2, and so on. This takes one pass over the pattern.

**Matching.** For each character in the longer string (the text), a single bitmask operation finds all candidate match positions, and isolating the lowest set bit selects the leftmost available match:

```rust
let pm_j = pm[text[j] as usize] & bound_mask & !p_flag;
p_flag |= pm_j & pm_j.wrapping_neg();  // isolate lowest set bit
t_flag |= u64::from(pm_j != 0) << j;
```

Three values interact here. `pm[text[j]]` gives every position in the pattern where this character appears. `bound_mask` restricts candidates to those within the Jaro matching window. `!p_flag` excludes positions that have already been matched. The result, `pm_j`, contains all valid match candidates. Isolating the lowest set bit (`x & -x`) selects the leftmost one, which preserves the greedy left-to-right matching behavior of the standard algorithm.

The `bound_mask` slides across the pattern as the text position advances: growing during the first phase (while the left edge of the window is pinned at position 0), then shifting once the window is fully open.

**Transpositions.** After matching, `p_flag` and `t_flag` encode which pattern and text positions were matched. Walking both from lowest to highest bit, the algorithm checks whether each pair's characters agree by testing the matched pattern bit against the character's bitmask:

```rust
while t_flag != 0 {
    let pat_bit = p_flag & p_flag.wrapping_neg();
    let t_pos = t_flag.trailing_zeros() as usize;
    if pm[text[t_pos] as usize] & pat_bit == 0 {
        transpositions += 1;
    }
    t_flag &= t_flag - 1;  // clear lowest set bit
    p_flag ^= pat_bit;
}
```

No character extraction. No temporary objects. Each iteration is a handful of bitwise operations and an indexed lookup.

### Why This Beats rapidfuzz

The algorithm is the same family: both implementations use bitparallel matching with `u64` bitmasks. The performance difference comes from the implementation context.

rapidfuzz is a general-purpose library. It handles arbitrary Unicode via a hash map fallback for non-ASCII characters, supports configurable score cutoffs with early termination, and accommodates strings of any length through multi-word bitmask arrays. Each of these features adds branches and indirection in the hot path.

The Rust implementation is specialized. It operates on raw byte slices, assumes strings fit in a single `u64` (under 64 bytes, which covers all course names), and computes every score unconditionally. The resulting code is a tight sequence of bitwise operations with no branching in the inner loop, which the compiler can optimize aggressively.

The tradeoff is clear: rapidfuzz handles everything, the Rust version handles exactly one workload. For that workload, the specialization pays off at ~2x.

---

## 5. When (and When Not) to Reach for Rust

Not every slow function justifies a Rust rewrite. And not every slow function needs one.

**Try a library first.**
For common operations like string similarity, cosine distance, or edit distance, there are excellent C-backed Python libraries (rapidfuzz, scipy, numpy) that will get you most of the way. rapidfuzz delivers 54x over pure Python with zero compilation step. For many workloads, that is enough.

**Reach for Rust when:**

* A C-backed library exists but you need the last factor of 2x on a latency-critical path
* No suitable library exists for your specific computation
* You have a tight loop over primitive data that runs on the order of one million iterations or more
* The function sits on the synchronous critical path and the interface can remain narrow

**Do not bother when:**

* The bottleneck is I/O such as LLM calls or database access
* An existing library already meets your latency requirements
* The function is already sub-millisecond in Python
* The logic depends heavily on Python objects or dynamic structures

The integration cost is lower than expected. PyO3 and maturin handle most of the build process. You write standard Rust, run a single command, and import the result into Python. A pure Python fallback keeps development and CI simple while production benefits from the speedup. The same test suite can validate both paths.

For this case, about 140 lines of Rust took an afternoon to write. The performance improvement is permanent.

---

## 6. Conclusion

The next set of performance gains in agent systems is not primarily in the model. It is in the orchestration layer.

Python remains the right choice for the majority of agent infrastructure, including prompt construction, tool dispatch, state management, and integration. For CPU-bound work between LLM calls, C-backed libraries like rapidfuzz can eliminate most of the overhead with no compilation required. That should be the first move.

But when a library gets you to 3 milliseconds and you need 1.5, a purpose-built Rust function via PyO3 can close the remaining gap. The Rust implementation in this project beats rapidfuzz by ~2x and pure Python by ~107x on the function that was actually bottlenecking the agent. Course name resolution across a 4,900 entry catalog dropped to under 1 millisecond per query.

The threshold for introducing Rust is higher than "faster than Python" and lower than most people think. If there is a hot loop on the critical path where even the best library is not fast enough, it is often worth doing.

---

## Appendix

### A. Benchmark Methodology

- **Runtime:** Python 3.12, Rust 1.93, PyO3 0.28, rapidfuzz 3.14
- **Build:** `maturin develop --release` (single-threaded, release optimizations)
- **Measurement:** Median of 100 iterations per workload, 3 warmup runs discarded
- **Overhead included:** All speedup figures include the cost of Python-to-Rust data conversion (`str` to `&str`). Pure compute speedups are higher.
- **Test data:** 40 realistic McGill course name variants (full and abbreviated forms), randomly sampled into 10,000 pairings with a fixed seed for reproducibility.

### Full Results

| Function | Workload | Python | rapidfuzz (C++) | Rust (PyO3) | vs Python | vs rapidfuzz |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| jaro_winkler | 10k string pairs | 171.7ms | 3.2ms | 1.6ms | **~107x** | **~2x** |

- rapidfuzz uses a C++ bitparallel Jaro-Winkler with Unicode support, hash-map fallback for non-ASCII, configurable score cutoffs, and multi-word bitmask arrays for arbitrary-length strings
- The Rust implementation uses the same bitparallel family but is specialized: raw byte slices, single `u64` bitmask (strings under 64 bytes), no branching in the inner loop
- The naive Rust port (identical algorithm to Python, no bitparallel optimization) ran in ~12ms, a ~14x speedup from language overhead alone
- The function falls back to pure Python gracefully if the Rust extension is not compiled
- Build: `maturin develop --release` — compiles in under 10 seconds

---

*Joshua Engroff · Rust Acceleration Benchmarks · PyO3 0.28 · April 2026*
