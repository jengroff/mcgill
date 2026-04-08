# Rust at the Chokepoints

*Accelerating CPU-bound work in agentic pipelines*

> **TL;DR:** I dropped a single Rust function into a Python agentic platform via PyO3 and measured a ~107x speedup over pure Python and a ~2x speedup over rapidfuzz, the strongest C++-backed string matching library in Python. This post walks through the benchmark, explains how a bitparallel Jaro-Winkler implementation in Rust outperforms both, and argues that selective Rust acceleration is one of the highest-leverage performance moves available to agent builders.

---

## 1. The Problem: Agents Aren't Just Waiting on LLMs

There is a comfortable assumption in the agentic AI community that most wall clock time is spent waiting on LLM API calls, so the speed of the orchestration layer does not matter. Python is fine. It is glue code. The model is the bottleneck.

That holds right up until you are fuzzy matching a user query against 4,900 course names.

In practice, every LLM call in a production agent pipeline is surrounded by CPU-bound orchestration work. The agent resolves entities by matching user input against large record sets, normalizing and comparing strings across thousands of candidates before the model ever sees them. These stages run synchronously on the critical path, so when they take hundreds of milliseconds they effectively serialize the entire decision loop.

The problem compounds with scale. Fuzzy matching 10,000 string pairs in pure Python takes roughly 172 milliseconds per batch, which adds up quickly when resolving course names, prerequisite references, and advisor lookups across a full catalog.

At these workloads, the orchestration layer becomes the bottleneck rather than the model.

I encountered this firsthand while building a Claude-powered course advisor for McGill University. The platform scrapes, resolves, embeds, and serves roughly 4,900 courses across 12 faculties via a LangGraph agent with a React frontend. Entity resolution, matching inputs like “Intro Organic Chem” to “CHEM 212: Introduction to Organic Chemistry 1,” sits directly on the critical path before every retrieval call.

So I decided to see what Rust could do about it.

---

## 2. The Approach: Surgical Rust via PyO3

The strategy was deliberately narrow. Do not rewrite the platform, rewrite the inner loop.

I identified one function where Python’s per element overhead dominated runtime, wrote a Rust equivalent using PyO3, and exposed it as a native Python extension module. The total investment was about 140 lines of Rust, compiled via `maturin develop --release` in under ten seconds.

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

Each query triggers roughly 4,900 string comparisons. Batch resolution of a dozen queries means tens of thousands of comparisons per request. This is exactly the profile where Rust performs well: a tight loop over primitive data, running synchronously on the critical path, with no I/O to hide behind.

---

## 3. The Results

The first question any experienced Python developer should ask is why not use rapidfuzz. It is the standard library for fast string matching in Python, backed by a C++ implementation using bitparallel algorithms. It is a `pip install` away.

So I benchmarked against it.

|                     |        Time |  vs Python | vs rapidfuzz |
| ------------------- | ----------: | ---------: | -----------: |
| **Python**          | **171.7ms** |            |              |
| **rapidfuzz (C++)** |   **3.2ms** |  **53.7x** |              |
| **Rust (PyO3)**     |   **1.6ms** | **107.3x** |     **2.0x** |

*10,000 string pairs, median of 100 iterations, 3 warmup runs discarded. Python 3.12, Rust 1.93, PyO3 0.28, rapidfuzz 3.14. Single threaded, release build. Speedups include the cost of Python-to-Rust data conversion. The Rust versus rapidfuzz ratio varies from roughly 1.8x to 2.2x across runs due to sub-millisecond measurement noise.*

The Rust implementation is roughly 2x faster than rapidfuzz and about 107x faster than pure Python. Both implementations use bitparallel Jaro-Winkler, so the difference is not algorithmic. It is a matter of implementation.

rapidfuzz is designed to be general. It supports Unicode normalization, score cutoffs with early termination, and arbitrary length strings. Each of those features introduces branches and indirection in the hot path.

The Rust implementation is specialized. It operates on raw byte slices, assumes strings fit within a single `u64`, and computes every score unconditionally. The result is a tight sequence of bitwise operations with minimal branching, which the compiler can optimize aggressively.

The test data uses realistic course name pairs such as “Introduction to Organic Chemistry” versus “Intro Organic Chem,” “Advanced Calculus” versus “Calculus 1,” and “Neuroanatomy and Neurophysiology” versus “Neuroanatomy,” sampled into 10,000 random pairings.

In practice, resolving a course name against the full 4,900 entry catalog takes under 1 millisecond per query with the Rust implementation, compared to about 1.6 milliseconds with rapidfuzz and 84 milliseconds in pure Python. A batch of 10 queries completes in about 8 milliseconds, which is the difference between a noticeable pause and an immediate response.

---

## 4. Deep Dive: Naive to Bitparallel

### Why Naive Rust is Already Fast

The first implementation was a direct port of the Python Jaro-Winkler algorithm into Rust, with the same structure and data flow. That version ran in about 12 milliseconds on the benchmark, roughly a 14x speedup over Python. The improvement came entirely from how the two languages execute identical logic.

In Python, each character comparison allocates a temporary string object, boolean updates involve reference counting, and loop iteration requires iterator objects and method dispatch. In Rust, the same operations compile down to byte comparisons, simple memory writes, and register-level loops.

That gap alone explains the initial speedup.

But 14x is not competitive with rapidfuzz, which achieves roughly 54x by using a more efficient algorithm. To close that gap, the Rust implementation needed to adopt the same approach.

---

### Bitparallel Jaro-Winkler

The bitparallel approach eliminates the inner loop of the matching pass. Instead of scanning the match window character by character, it encodes character positions as bitmasks and resolves each match with a small number of bitwise operations.

**Preprocessing** builds a lookup table mapping each byte value to a bitmask of positions in the pattern.

**Matching** reduces each comparison to a handful of bitwise operations, intersecting candidate positions, applying window constraints, and selecting the leftmost available match.

**Transpositions** operate on bit flags rather than extracted characters, walking matched positions through bit operations rather than index-based loops.

The result is that each iteration becomes a small number of arithmetic and bitwise instructions, with no allocation and minimal branching.

---

### Why This Beats rapidfuzz

The algorithm is the same family, so the difference comes from context.

rapidfuzz is a general-purpose library. It supports Unicode, variable-length strings, and configurable behavior. That flexibility introduces additional branching and logic in the hot path.

The Rust implementation is narrowly scoped. It assumes short ASCII strings, fits everything into a single machine word, and avoids conditional logic in the inner loop. That specialization allows the compiler to generate highly optimized code.

The tradeoff is straightforward. rapidfuzz handles a wide range of inputs. The Rust version handles exactly one workload. For that workload, the specialization yields roughly a 2x gain.

---

## 5. When (and When Not) to Reach for Rust

Not every slow function justifies a Rust rewrite, and not every slow function needs one.

**Try a library first.**
For common operations such as string similarity, cosine distance, or edit distance, C-backed Python libraries such as rapidfuzz, scipy, and numpy will get you most of the way. rapidfuzz alone delivers roughly 54x over pure Python.

**Reach for Rust when:**

* A C-backed library exists but does not meet your latency target
* No suitable library exists for the computation
* The workload is a tight loop over primitive data
* The function sits on the synchronous critical path
* The interface can remain narrow and well defined

**Do not bother when:**

* The bottleneck is I/O such as LLM calls or database access
* An existing library already meets your requirements
* The function is already sub-millisecond in Python
* The logic depends heavily on Python objects

The integration cost is lower than it appears. PyO3 and maturin handle most of the build process. A pure Python fallback keeps development and CI simple, while production benefits from the compiled extension. The same test suite can validate both paths.

In this case, about 140 lines of Rust took an afternoon to write. The performance improvement is permanent.

---

## 6. Conclusion

The next set of performance gains in agent systems is not primarily in the model. It is in the orchestration layer.

Python remains the right choice for most agent infrastructure, including prompt construction, tool dispatch, state management, and integration. For CPU-bound work between LLM calls, C-backed libraries such as rapidfuzz should be the first step.

But when a library gets you to 3 milliseconds and you need 1.5, a purpose-built Rust function via PyO3 can close the remaining gap. In this case, the Rust implementation outperforms rapidfuzz by roughly 2x and pure Python by roughly 107x on the function that was actually bottlenecking the agent. Course name resolution across a 4,900 entry catalog dropped to under 1 millisecond per query.

The threshold for introducing Rust is higher than “faster than Python” and lower than most people assume. If there is a hot loop on the critical path and even the best available library is not sufficient, it is usually worth doing.

Most performance work in agent systems will not come from changing models or rewriting stacks. It comes from identifying where the time actually goes and fixing that one place.
