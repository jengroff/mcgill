# Stanchion Integration Guide for McGill Course Explorer

## What is Stanchion?

Stanchion is a framework-agnostic reliability layer for LLM agent pipelines. It provides:

- **Input/output contracts** — Pydantic schema validation at every node boundary
- **Failure classification & retry** — automatic categorization of errors (recoverable, terminal, ambiguous) with jittered backoff
- **Cost/token budgets** — per-run caps to prevent runaway API spend
- **Checkpointing** — resume a failed run from the last successful node
- **Execution tracing** — full audit trail of every node invocation, timing, and failure

## Why it matters for this project

The mcgill backend has two LangGraph workflows:

1. **Retrieval** — `keyword → semantic → program → graph → structured → fusion`
2. **Synthesis** — `context_pack → synthesize`

Currently, every node wraps its body in `try/except` and returns empty results on failure. This means:

- A failed semantic search silently degrades fusion quality with no signal
- A Claude API timeout in `structured_node` or `synthesize_node` is not retried
- There is no budget cap — a malformed query could loop through text-to-SQL retries indefinitely
- If synthesis fails, all 6 retrieval steps must re-run from scratch

Stanchion addresses all of these.

## Integration approach

### 1. Define contracts for each node

Create Pydantic models for the expected input/output shape of each workflow node:

```python
from pydantic import BaseModel
from stanchion import NodeContract, ContractRegistry

# Retrieval node contracts
class RetrievalInput(BaseModel):
    query: str
    top_k: int = 10

class KeywordOutput(BaseModel):
    keyword_results: list[dict]

class SemanticOutput(BaseModel):
    semantic_results: list[dict]

class FusionOutput(BaseModel):
    fused_results: list[dict]
    status: str

# Synthesis node contracts
class SynthesizeInput(BaseModel):
    query: str
    sources: list[dict]
    conversation_history: list[dict] = []

class SynthesizeOutput(BaseModel):
    response: str
    status: str

# Register
registry = ContractRegistry()
registry.register(NodeContract(node_id="keyword", input_schema=RetrievalInput, output_schema=KeywordOutput))
registry.register(NodeContract(node_id="semantic", input_schema=RetrievalInput, output_schema=SemanticOutput))
registry.register(NodeContract(node_id="fusion", input_schema=RetrievalInput, output_schema=FusionOutput))
registry.register(NodeContract(node_id="synthesize", input_schema=SynthesizeInput, output_schema=SynthesizeOutput))
```

### 2. Wrap the LangGraph with LangGraphAdapter

Decorate existing node functions and let the adapter intercept calls:

```python
from stanchion import LangGraphAdapter
from stanchion.adapters.langgraph import armature_langgraph_node

@armature_langgraph_node("semantic", NodeContract(
    node_id="semantic",
    input_schema=RetrievalInput,
    output_schema=SemanticOutput,
))
async def semantic_node(state):
    # existing logic unchanged
    ...

# After building the StateGraph
adapter = LangGraphAdapter(registry, runner=None)
validated_graph = adapter.wrap(compiled_graph)
```

The adapter validates inputs before each node runs and validates outputs after, raising `ContractViolation` (classified as `TERMINAL`) if the shape is wrong.

### 3. Add retry policies for LLM-calling nodes

The `structured_node` (text-to-SQL via Claude Haiku) and `synthesize_node` (Claude Sonnet) are the most failure-prone. Configure retry policies:

```python
from stanchion import RunConfig, ExecutionBudget
from stanchion.failures import FailureClass, FailurePolicy

config = RunConfig(
    budget=ExecutionBudget(
        max_tokens_total=50_000,   # cap total tokens per run
        max_cost_usd=0.10,        # cap spend per run
        max_latency_ms=30_000,    # 30s wall-clock cap
    ),
    policy_map={
        FailureClass.RECOVERABLE: FailurePolicy(max_retries=3, backoff_seconds=2.0),
        FailureClass.TERMINAL: FailurePolicy(max_retries=0, backoff_seconds=0.0),
        FailureClass.AMBIGUOUS: FailurePolicy(max_retries=1, backoff_seconds=1.0),
    },
)
```

With this config:
- A `TimeoutError` from the Claude API → `RECOVERABLE` → retried up to 3 times with jittered backoff (0 to 2s)
- A `ContractViolation` from malformed SQL output → `TERMINAL` → pipeline stops, error surfaces to user
- A `ValueError` from unexpected response shape → `AMBIGUOUS` → retried once

### 4. Checkpoint for resume-from-failure

Use `InMemoryStore` for development or `RedisStore` for production:

```python
from stanchion import CheckpointManager, InMemoryStore, RedisStore

# Development
store = InMemoryStore()

# Production (reuse existing Redis if available)
store = RedisStore("redis://localhost:6379", ttl_seconds=3600)

checkpoint_mgr = CheckpointManager(store)
```

If synthesis fails, the next run can resume from the `context_pack` node without re-running all retrieval steps:

```python
config = RunConfig(
    budget=ExecutionBudget.unlimited(),
    resume_from="context_pack",
)
```

### 5. Execution tracing for observability

Every node invocation is recorded in an `ExecutionTrace` with timing, input/output snapshots, and failure details:

```python
result = await runner.run(node_sequence, initial_state)

# Inspect failures
for event in result.trace.failures():
    print(f"{event.node_id} attempt {event.attempt}: {event.failure_message}")

# Export full trace as JSON for logging/debugging
trace_json = result.trace.to_json()

# Compare two runs to find logical differences (ignoring timing)
diffs = trace_a.diff(trace_b)
```

## Files that would change

| File | Change |
|------|--------|
| `pyproject.toml` | Add `stanchion` dependency |
| `backend/workflows/retrieval/contracts.py` | New — Pydantic schemas for retrieval nodes |
| `backend/workflows/synthesis/contracts.py` | New — Pydantic schemas for synthesis nodes |
| `backend/workflows/retrieval/graph.py` | Wrap graph with `LangGraphAdapter` |
| `backend/workflows/synthesis/graph.py` | Wrap graph with `LangGraphAdapter` |
| `backend/workflows/retrieval/nodes.py` | Decorate nodes with `@armature_langgraph_node`, remove bare try/except |
| `backend/workflows/synthesis/nodes.py` | Decorate nodes, remove bare try/except |
