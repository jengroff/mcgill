# Stroma Integration Plan for McGill Course Explorer

## What is Stroma?

Stroma is a **reliability framework for LLM/agent pipelines** (Python 3.12+). It does not replace LangGraph — it wraps around it, adding reliability primitives that LangGraph does not provide:

- **Input/output contracts** — Pydantic schema validation at every node boundary
- **Failure classification & retry** — automatic categorization of errors (`RECOVERABLE`, `TERMINAL`, `AMBIGUOUS`) with jittered backoff
- **Cost/token budgets** — per-run caps on tokens, USD, and wall-clock latency
- **Checkpointing** — resume a failed run from the last successful node (in-memory or Redis)
- **Execution tracing** — full audit trail of every node invocation, timing, and failure
- **Lifecycle hooks** — async callbacks for observability (OpenTelemetry, Datadog, etc.)

Install: `uv add stroma[langgraph,redis]`

## Why it matters for this project

The mcgill backend has 5 LangGraph workflows, each with multiple LLM calls:

| Workflow | Nodes | LLM calls | Failure risk |
|----------|-------|-----------|--------------|
| **Retrieval** | keyword → semantic → program → graph → structured → fusion | Claude Haiku (text-to-SQL), Voyage AI (embeddings) | API timeouts, malformed SQL, empty results |
| **Synthesis** | context_pack → synthesize | Claude Sonnet | API timeout, token limits |
| **Ingestion** | extract → chunk → embed → store | Voyage AI (batch embed) | Long-running, partial progress lost |
| **Ingest** | scrape → resolve → embed | Voyage AI, Playwright | Hours-long runs, network failures |
| **Planner** | gather_context → plan_agent | Claude Agent SDK | Expensive, unpredictable cost |

**Current pain points Stroma addresses:**

1. **Silent degradation** — Every node wraps its body in `try/except` and returns empty results on failure. A failed semantic search silently degrades fusion quality with no signal to the user or logs.
2. **No retries** — A Claude API timeout in `structured_node` or `synthesize_node` is not retried. The user gets an empty response.
3. **No cost controls** — The planner runs Claude Agent SDK with file tools. A malformed prompt could loop indefinitely with no budget cap.
4. **No checkpointing** — If synthesis fails after a 6-node retrieval pipeline, all retrieval steps must re-run. If the ingest pipeline fails 45 minutes into a scrape, all progress is lost.
5. **No structured observability** — Failures are logged ad-hoc via `logger.warning()` with no centralized trace or audit trail.

---

## Phase 1: LangGraph Adapter on Retrieval + Synthesis

**Goal:** Add contract validation to the two most-used workflows without restructuring any pipeline code.

**Why start here:** The retrieval pipeline has 6 nodes in sequence, each producing different output shapes. Today, if `structured_node` returns malformed data, `fusion_node` silently produces garbage results. Contracts catch this at the boundary.

### Step 1 — Define contracts for retrieval nodes

Create Pydantic models for the expected input/output shape of each node:

```python
# backend/workflows/retrieval/contracts.py
from pydantic import BaseModel
from stroma import NodeContract

class RetrievalInput(BaseModel):
    query: str
    top_k: int = 10
    mode: str = "hybrid"

class KeywordOutput(BaseModel):
    keyword_results: list[dict]

class SemanticOutput(BaseModel):
    semantic_results: list[dict]

class ProgramOutput(BaseModel):
    program_results: list[dict]

class GraphOutput(BaseModel):
    graph_context: str

class StructuredOutput(BaseModel):
    structured_context: str

class FusionOutput(BaseModel):
    fused_results: list[dict]

# Contract registry
keyword_contract = NodeContract(node_id="keyword", input_schema=RetrievalInput, output_schema=KeywordOutput)
semantic_contract = NodeContract(node_id="semantic", input_schema=RetrievalInput, output_schema=SemanticOutput)
program_contract = NodeContract(node_id="program", input_schema=RetrievalInput, output_schema=ProgramOutput)
graph_contract = NodeContract(node_id="graph", input_schema=RetrievalInput, output_schema=GraphOutput)
structured_contract = NodeContract(node_id="structured", input_schema=RetrievalInput, output_schema=StructuredOutput)
fusion_contract = NodeContract(node_id="fusion", input_schema=RetrievalInput, output_schema=FusionOutput)
```

### Step 2 — Define contracts for synthesis nodes

```python
# backend/workflows/synthesis/contracts.py
from pydantic import BaseModel
from stroma import NodeContract

class SynthesisInput(BaseModel):
    query: str
    retrieval_context: list[dict]
    program_context: list[dict] = []
    graph_context: str = ""
    structured_context: str = ""
    conversation_history: list[dict] = []

class ContextPackOutput(BaseModel):
    packed_context: str

class SynthesizeOutput(BaseModel):
    response: str
    sources: list[dict]

context_pack_contract = NodeContract(node_id="context_pack", input_schema=SynthesisInput, output_schema=ContextPackOutput)
synthesize_contract = NodeContract(node_id="synthesize", input_schema=SynthesisInput, output_schema=SynthesizeOutput)
```

### Step 3 — Decorate existing nodes and wrap graphs

Apply the `@stroma_langgraph_node` decorator to existing node functions. This does not change the function body — it only registers the node for the adapter to intercept:

```python
# backend/workflows/retrieval/nodes.py
from stroma.adapters.langgraph import stroma_langgraph_node
from backend.workflows.retrieval.contracts import keyword_contract, semantic_contract, ...

@stroma_langgraph_node("keyword", keyword_contract)
async def keyword_node(state: RetrievalState) -> RetrievalState:
    # existing logic unchanged
    ...

@stroma_langgraph_node("structured", structured_contract)
async def structured_node(state: RetrievalState) -> RetrievalState:
    # existing logic unchanged
    ...
```

In the orchestrator, wrap the compiled graph:

```python
# backend/workflows/retrieval/graph.py
from stroma import ContractRegistry, StromaRunner
from stroma.adapters.langgraph import LangGraphAdapter
from backend.workflows.retrieval.contracts import (
    keyword_contract, semantic_contract, program_contract,
    graph_contract, structured_contract, fusion_contract,
)

class RetrievalOrchestrator(WorkflowOrchestrator):
    def build_graph(self) -> CompiledStateGraph:
        graph = StateGraph(RetrievalState)
        # ... existing node additions and edges ...
        compiled = graph.compile()

        # Wrap with Stroma contract validation
        registry = ContractRegistry()
        for c in [keyword_contract, semantic_contract, program_contract,
                   graph_contract, structured_contract, fusion_contract]:
            registry.register(c)
        adapter = LangGraphAdapter(registry, runner=None)
        return adapter.wrap(compiled)
```

**What this buys you:** Every node's input and output is validated against its Pydantic schema. A `ContractViolation` is raised immediately when a node returns malformed data — classified as `TERMINAL` (no retries, because the data shape won't fix itself). This replaces silent degradation with explicit, catchable errors.

**What doesn't change:** Node function bodies, graph topology, state TypeDicts, API routes — all untouched.

---

## Phase 2: StromaRunner for Ingestion Pipeline

**Goal:** Add checkpointing and retries to the long-running ingest pipeline so failures don't lose hours of progress.

**Why this pipeline:** The ingest workflow (scrape → resolve → embed) can run for hours on large faculties. Today, if embedding fails after 45 minutes of scraping, everything must restart from zero. Stroma's checkpoint store solves this directly.

### Step 1 — Create a Stroma service layer

```python
# backend/services/stroma/__init__.py
from backend.services.stroma.runner import create_runner, anthropic_classifier

# backend/services/stroma/runner.py
from stroma import StromaRunner
from stroma.failures import FailureClass
from backend.config import settings

def anthropic_classifier(exc, ctx):
    """Classify Anthropic SDK exceptions."""
    import anthropic
    if isinstance(exc, anthropic.RateLimitError):
        return FailureClass.RECOVERABLE
    if isinstance(exc, anthropic.AuthenticationError):
        return FailureClass.TERMINAL
    if isinstance(exc, anthropic.APITimeoutError):
        return FailureClass.RECOVERABLE
    if isinstance(exc, anthropic.BadRequestError):
        return FailureClass.TERMINAL
    return None

def create_runner(**kwargs) -> StromaRunner:
    """Factory for a pre-configured StromaRunner."""
    runner = StromaRunner.quick()
    if settings.redis_url:
        runner = runner.with_redis(settings.redis_url)
    runner = runner.with_classifiers([anthropic_classifier])
    return runner
```

### Step 2 — Add configuration

```python
# backend/config.py — add to Settings
class Settings(BaseSettings):
    # ... existing fields ...
    redis_url: str = ""  # empty = in-memory checkpoints
    stroma_budget_tokens: int = 200_000
    stroma_budget_usd: float = 5.0
```

### Step 3 — Convert ingest nodes to Stroma nodes

```python
# backend/workflows/ingest/stroma_graph.py
from pydantic import BaseModel
from backend.services.stroma import create_runner

class ScrapeInput(BaseModel):
    faculty_filter: str | None = None
    dept_filter: str | None = None
    max_course_pages: int = 5000

class ScrapeOutput(BaseModel):
    courses_scraped: int

class ResolveOutput(BaseModel):
    entities_created: int
    relationships_created: int

class EmbedOutput(BaseModel):
    chunks_created: int

runner = create_runner()

@runner.node("scrape", input=ScrapeInput, output=ScrapeOutput)
async def scrape(state: ScrapeInput) -> dict:
    # existing scrape_node logic
    ...
    return {"courses_scraped": count}

@runner.node("resolve", input=ScrapeOutput, output=ResolveOutput)
async def resolve(state: ScrapeOutput) -> dict:
    # existing resolve_node logic
    ...
    return {"entities_created": nodes, "relationships_created": rels}

@runner.node("embed", input=ResolveOutput, output=EmbedOutput)
async def embed(state: ResolveOutput) -> dict:
    # existing embed_node logic
    ...
    return {"chunks_created": chunks}
```

### Step 4 — Run with checkpointing and resume

```python
# Normal execution
result = await runner.run([scrape, resolve, embed], {
    "faculty_filter": "science",
    "max_course_pages": 5000,
})

# Resume after failure (e.g., embed failed, scrape+resolve already done)
result = await runner.run(
    [scrape, resolve, embed],
    {"faculty_filter": "science"},
    config=RunConfig(run_id="same-run-id", resume_from="embed"),
)
# scrape and resolve are skipped — their outputs loaded from checkpoint store
```

**What this buys you:**
- **Checkpointing** — after each successful node, state is persisted. Redis store survives container restarts.
- **Automatic retries** — a `RateLimitError` from Voyage AI during embedding is retried 3 times with jittered backoff.
- **Resume** — the API route or CLI can store the `run_id` and resume from the last successful node on failure.

---

## Phase 3: Cost Tracking + Budget Guards on Planner

**Goal:** Prevent runaway costs on the planner workflow, which uses Claude Agent SDK with unpredictable token usage.

### Step 1 — Budget-capped runner for the planner

```python
# backend/workflows/planner/graph.py
from stroma import StromaRunner, RunConfig, ExecutionBudget
from stroma.failures import FailureClass, FailurePolicy
from backend.services.stroma import create_runner, anthropic_classifier

runner = create_runner().with_budget(
    tokens=100_000,    # hard cap: 100k tokens per plan
    cost_usd=5.00,     # hard cap: $5 per plan
    latency_ms=120_000, # hard cap: 2 minutes wall-clock
)
```

### Step 2 — Report usage from nodes

Stroma nodes report usage by returning tuples alongside their output dict. The runner uses built-in pricing tables for Claude models:

```python
@runner.node("gather_context", input=PlannerInput, output=ContextOutput)
async def gather_context(state: PlannerInput) -> dict:
    # ... existing gather_context_node logic ...
    return {"candidate_courses": courses, "program_requirements": reqs}

@runner.node("plan_agent", input=ContextOutput, output=PlanOutput)
async def plan_agent(state: ContextOutput) -> tuple:
    # ... existing plan_agent_node logic with Claude SDK ...
    result = await client.messages.create(...)
    usage = result.usage

    return (
        {"plan_markdown": md, "plan_semesters": semesters},
        usage.input_tokens,
        usage.output_tokens,
        "claude-sonnet-4-6",  # model hint for cost calculation
    )
```

### Step 3 — Surface cost to users via SSE

```python
# backend/api/routes/chat.py — in _run_planner_bg()
result = await runner.run([gather_context, plan_agent], initial_state)

queue.put_nowait({
    "type": "assistant",
    "content": result.outputs["plan_agent"]["plan_markdown"],
})
queue.put_nowait({
    "type": "step_update",
    "phase": "planner",
    "label": f"Plan complete — {result.total_tokens:,} tokens (${result.total_cost_usd:.3f})",
    "status": "done",
})
```

**What this buys you:**
- **Budget enforcement** — `BudgetExceeded` is raised if the planner exceeds token/cost/latency limits. Classified as `RECOVERABLE` by default (retried once in case it was a fluke).
- **Cost visibility** — every planner run reports total tokens and USD cost, surfaced to the user.
- **Per-node policies** — the expensive `plan_agent` node can have a lower retry limit (1 retry instead of 3) to avoid doubling cost on repeated failures.

---

## Phase 4: Observability Hooks

**Goal:** Replace ad-hoc `logger.warning()` calls with structured lifecycle hooks that feed into centralized observability.

### Step 1 — Define hooks

```python
# backend/services/stroma/hooks.py
import logging
from stroma import NodeHooks

logger = logging.getLogger("stroma")

async def on_start(run_id: str, node_id: str, input_state: dict):
    logger.info(f"[{run_id}] {node_id} started", extra={
        "run_id": run_id, "node_id": node_id,
    })

async def on_success(run_id: str, node_id: str, output_state: dict, tokens_used: int):
    logger.info(f"[{run_id}] {node_id} done ({tokens_used} tokens)", extra={
        "run_id": run_id, "node_id": node_id, "tokens": tokens_used,
    })

async def on_failure(run_id: str, node_id: str, exc: Exception, failure_class):
    logger.error(f"[{run_id}] {node_id} {failure_class.name}: {exc}", extra={
        "run_id": run_id, "node_id": node_id, "failure_class": failure_class.name,
    })

hooks = NodeHooks(
    on_node_start=on_start,
    on_node_success=on_success,
    on_node_failure=on_failure,
)
```

### Step 2 — Attach to runners

```python
# backend/services/stroma/runner.py
from backend.services.stroma.hooks import hooks

def create_runner(**kwargs) -> StromaRunner:
    runner = StromaRunner.quick()
    if settings.redis_url:
        runner = runner.with_redis(settings.redis_url)
    runner = runner.with_classifiers([anthropic_classifier])
    runner = runner.with_hooks(hooks)
    return runner
```

### Step 3 — Execution traces for debugging

```python
# Available on every run result
result = await runner.run(nodes, state)

# Inspect all failures across the run
for event in result.trace.failures():
    print(f"{event.node_id} attempt {event.attempt}: {event.failure_message}")

# Export full trace as JSON (useful for logging to a file or external system)
trace_json = result.trace.to_json()

# Compare two runs for regression detection
diffs = trace_a.diff(trace_b)
```

**What this buys you:**
- **Structured logs** — every node start/success/failure is logged with `run_id` and `node_id` as structured fields, queryable in any log aggregator.
- **Full traces** — complete audit trail of every node invocation, timing, input/output snapshots, and failures.
- **OpenTelemetry-ready** — swap the hook callbacks with OTel span management when you add tracing infrastructure. No pipeline code changes.

---

## Migration path

| Phase | Effort | Risk | Blast radius | Value |
|-------|--------|------|-------------|-------|
| **1. LangGraph Adapter** | Low — decorators + wrap call | Minimal — no logic changes | Retrieval + Synthesis graphs | Contract validation, catch silent failures |
| **2. Ingest StromaRunner** | Medium — refactor 3 nodes | Low — background pipeline only | Ingest workflow | Checkpointing, retries, resume-from-failure |
| **3. Planner Budgets** | Low — add budget + usage tuples | Minimal — additive | Planner workflow | Cost control, visibility |
| **4. Hooks** | Low — 3 callback functions | None — purely additive | All runners | Structured observability |

**Recommended order:** Phase 1 → 2 → 3 → 4. Each phase is independently deployable and valuable.

## Files that would change

| File | Change |
|------|--------|
| `pyproject.toml` | Add `stroma[langgraph,redis]` dependency |
| `backend/config.py` | Add `redis_url`, `stroma_budget_tokens`, `stroma_budget_usd` |
| `backend/services/stroma/__init__.py` | New — runner factory, classifiers |
| `backend/services/stroma/runner.py` | New — `create_runner()`, `anthropic_classifier()` |
| `backend/services/stroma/hooks.py` | New — lifecycle hook callbacks |
| `backend/workflows/retrieval/contracts.py` | New — Pydantic schemas for 6 retrieval nodes |
| `backend/workflows/synthesis/contracts.py` | New — Pydantic schemas for 2 synthesis nodes |
| `backend/workflows/retrieval/nodes.py` | Add `@stroma_langgraph_node` decorators |
| `backend/workflows/synthesis/nodes.py` | Add `@stroma_langgraph_node` decorators |
| `backend/workflows/retrieval/graph.py` | Wrap compiled graph with `LangGraphAdapter` |
| `backend/workflows/synthesis/graph.py` | Wrap compiled graph with `LangGraphAdapter` |
| `backend/workflows/ingest/stroma_graph.py` | New — StromaRunner version of ingest pipeline |
| `backend/workflows/planner/graph.py` | Add budget-capped runner, usage tuples |
| `backend/api/routes/chat.py` | Surface cost info in SSE events |
