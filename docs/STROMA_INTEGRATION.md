# Stroma Integration Guide for McGill Course Explorer

> **Stroma** is a reliability framework for async agent and LLM pipelines.
> *"dbt didn't replace your data warehouse. Stroma doesn't replace your agent framework."*
>
> It injects typed contracts, failure classification, retries, cost budgets, checkpointing,
> and execution tracing into pipeline execution — without replacing LangGraph.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Benefits for McGill](#2-benefits-for-mcgill)
3. [What Stroma Does NOT Replace](#3-what-stroma-does-not-replace)
4. [Phase 1 — Install + Contract Definitions](#4-phase-1--install--contract-definitions)
5. [Phase 2 — Wrap the Ingest Pipeline](#5-phase-2--wrap-the-ingest-pipeline)
6. [Phase 3 — Wrap Retrieval + Synthesis Pipelines](#6-phase-3--wrap-retrieval--synthesis-pipelines)
7. [Phase 4 — Budget Enforcement + Planner Safety](#7-phase-4--budget-enforcement--planner-safety)
8. [Phase 5 — Observability](#8-phase-5--observability)
9. [Docker + Infrastructure Changes](#9-docker--infrastructure-changes)
10. [Dependency Impact](#10-dependency-impact)

---

## 1. Architecture Overview

### Current McGill Pipeline Stack

```
Frontend (React 19 + Zustand)
  │  HTTP / SSE
FastAPI Router Layer
  │
WorkflowOrchestrator ABC ──► LangGraph StateGraph
  │
6 Workflows:
  ├─ ingest    (precheck → scrape → resolve → embed)
  ├─ retrieval (parallel: keyword, semantic, graph, structured → fusion)
  ├─ synthesis (context_pack → synthesize)
  ├─ ingestion (extract → chunk → embed → store)
  ├─ curriculum (interest_map → requirements → candidate → prereq → conflict → rank → assemble)
  └─ planner   (gather_context → plan_agent)
  │
PostgreSQL + pgvector  ←→  Neo4j 5
```

### Where Stroma Fits

```
WorkflowOrchestrator ABC
  │
  ├─ build_graph()
  │    └─ StateGraph ──► LangGraphAdapter.wrap(graph)  ◄── STROMA
  │
  ├─ run() / stream()
  │    └─ graph.ainvoke(state)
  │         ├─ Contract validation at every node boundary  ◄── STROMA
  │         ├─ Failure classification + retry with backoff  ◄── STROMA
  │         ├─ Cost tracking per node                      ◄── STROMA
  │         ├─ Checkpointing after each node success       ◄── STROMA
  │         └─ Full execution trace                        ◄── STROMA
  │
  └─ Existing SSE streaming + WorkflowRegistry ──► UNCHANGED
```

Stroma wraps the compiled LangGraph graph. It does not replace LangGraph, the orchestrator pattern, or the API layer.

---

## 2. Benefits for McGill

### 2.1 Contract Validation at Node Boundaries

McGill's workflows pass `TypedDict` state between nodes with no runtime validation. If `scrape_node` returns a dict missing `courses_scraped`, the error surfaces in `embed_node` — two steps later.

**Current code** (`backend/workflows/ingest/state.py`):

```python
class IngestState(BaseWorkflowState, total=False):
    faculty_filter: list[str] | None
    dept_filter: list[str] | None
    courses_scraped: int
    scrape_status: str  # "pending" | "complete" | "error"
    entities_created: int
    relationships_created: int
    resolve_status: str
    chunks_created: int
    embed_status: str
```

`total=False` means every field is optional at the type level. A node can return `{}` and nothing catches it until a downstream node reads a missing key.

Stroma's `NodeContract` + `BoundaryValidator` validates the output of every node immediately, raising `ContractViolation` (classified `TERMINAL`) at the exact boundary where bad data originates.

### 2.2 Retry + Failure Classification for External Services

McGill hits 4 external services that fail transiently:

| Service | Node(s) | Failure Mode |
|---------|---------|-------------|
| McGill website | `scrape_node` | Playwright timeouts, connection resets |
| Anthropic API | `synthesize_node`, `structured_node`, `plan_agent_node` | 529 overload, rate limits |
| Voyage AI | `semantic_node`, `embed_node` | Rate limits, timeouts |
| Neo4j | `graph_node`, `resolve_node` | Connection drops |

Today, any exception in any node returns an error dict and either silently degrades (retrieval) or aborts (ingest). Stroma classifies every error into one of three classes:

- **RECOVERABLE** (auto-retry with jittered backoff): rate limits, timeouts, connection resets
- **TERMINAL** (stop immediately): contract violations, invalid data
- **AMBIGUOUS** (retry once, short backoff): anything unrecognized

### 2.3 Ingest Pipeline Checkpointing

The full ingest pipeline processes ~4,900 courses across 12 faculties. If it fails at the `embed` step after scraping 2,000 courses, everything is re-scraped. The existing `pipeline_runs` table tracks only coarse status (`pending` / `running` / `complete` / `error`).

Stroma checkpointing persists each node's validated output. On failure, `resume_from="embed"` skips `precheck`, `scrape`, and `resolve`, loading the checkpoint from `resolve`'s output.

### 2.4 Cost Tracking + Budget Caps

McGill calls Claude Sonnet (synthesis, planner, structured SQL) and Voyage AI (embeddings) with no cost visibility. Stroma tracks tokens, USD cost, and latency per node, with built-in pricing for Claude models. A budget cap on the planner prevents runaway agentic loops.

### 2.5 Execution Tracing

Full audit trail of every node execution attempt — timing, input/output state, failure info, retry count. `ExecutionTrace.diff()` compares two runs to answer "why did the Tuesday ingest take 3x longer than Monday's?"

### 2.6 Parallel Node Guarantees

The retrieval workflow fans out 4 branches via `asyncio.gather` with `return_exceptions=True`. Stroma's `parallel()` adds per-branch contract validation, automatic output merging, and deterministic failure propagation.

---

## 3. What Stroma Does NOT Replace

| Layer | Status |
|-------|--------|
| LangGraph `StateGraph` structure | **Unchanged** — Stroma wraps the compiled graph |
| `WorkflowOrchestrator` ABC + `WorkflowRegistry` | **Unchanged** — still handles SSE streaming + route delegation |
| FastAPI routes, auth, CORS | **Unchanged** |
| PostgreSQL / pgvector / Neo4j | **Unchanged** |
| Frontend (React, Zustand, D3) | **Unchanged** |
| Docker Compose orchestration | **Minor addition** — Redis service for checkpointing |

---

## 4. Phase 1 — Install + Contract Definitions

### 4.1 Install Stroma

```bash
uv add "stroma[langgraph,redis]"
```

This installs:
- `stroma` core (Pydantic 2.0+ — already satisfied by McGill's `pydantic>=2.12.5`)
- `langgraph` adapter (already satisfied by McGill's `langgraph>=1.1.3`)
- `redis` async client for checkpointing

### 4.2 Create Contract Schemas

Create `backend/contracts/` with Pydantic models for each node boundary. These are separate from the existing `TypedDict` states — they define what each node **must** produce.

**`backend/contracts/__init__.py`**:

```python
from backend.contracts.ingest import (
    PrecheckInput,
    PrecheckOutput,
    ScrapeInput,
    ScrapeOutput,
    ResolveInput,
    ResolveOutput,
    EmbedInput,
    EmbedOutput,
)
from backend.contracts.retrieval import (
    RetrievalInput,
    KeywordOutput,
    SemanticOutput,
    GraphOutput,
    StructuredOutput,
    FusionInput,
    FusionOutput,
)
from backend.contracts.synthesis import (
    ContextPackInput,
    ContextPackOutput,
    SynthesizeInput,
    SynthesizeOutput,
)
from backend.contracts.planner import (
    GatherContextInput,
    GatherContextOutput,
    PlanAgentInput,
    PlanAgentOutput,
)
```

**`backend/contracts/ingest.py`**:

```python
from pydantic import BaseModel, Field


class PrecheckInput(BaseModel):
    run_id: str
    faculty_filter: list[str] | None = None
    dept_filter: list[str] | None = None
    force: bool = False


class PrecheckOutput(BaseModel):
    skipped_depts: list[str] = Field(default_factory=list)
    active_depts: list[str] = Field(default_factory=list)


class ScrapeInput(BaseModel):
    run_id: str
    active_depts: list[str]
    faculty_filter: list[str] | None = None
    dept_filter: list[str] | None = None
    max_course_pages: int | None = None
    max_program_pages: int | None = None


class ScrapeOutput(BaseModel):
    courses_scraped: int = Field(ge=0)
    scrape_status: str = Field(pattern=r"^(complete|error)$")


class ResolveInput(BaseModel):
    run_id: str
    active_depts: list[str]


class ResolveOutput(BaseModel):
    entities_created: int = Field(ge=0)
    relationships_created: int = Field(ge=0)
    resolve_status: str = Field(pattern=r"^(complete|error)$")


class EmbedInput(BaseModel):
    run_id: str
    active_depts: list[str]


class EmbedOutput(BaseModel):
    chunks_created: int = Field(ge=0)
    embed_status: str = Field(pattern=r"^(complete|error)$")
```

**`backend/contracts/retrieval.py`**:

```python
from pydantic import BaseModel, Field


class RetrievalInput(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)
    mode: str = Field(default="hybrid", pattern=r"^(keyword|semantic|hybrid)$")


class KeywordOutput(BaseModel):
    keyword_results: list[dict] = Field(default_factory=list)


class SemanticOutput(BaseModel):
    semantic_results: list[dict] = Field(default_factory=list)
    program_results: list[dict] = Field(default_factory=list)


class GraphOutput(BaseModel):
    graph_context: str = ""


class StructuredOutput(BaseModel):
    structured_context: str = ""


class FusionInput(BaseModel):
    query: str
    top_k: int = 10
    keyword_results: list[dict] = Field(default_factory=list)
    semantic_results: list[dict] = Field(default_factory=list)


class FusionOutput(BaseModel):
    fused_results: list[dict] = Field(default_factory=list)
    status: str = "complete"
```

**`backend/contracts/synthesis.py`**:

```python
from pydantic import BaseModel, Field


class ContextPackInput(BaseModel):
    query: str
    retrieval_context: list[dict] = Field(default_factory=list)
    program_context: list[dict] = Field(default_factory=list)
    graph_context: str = ""
    structured_context: str = ""


class ContextPackOutput(BaseModel):
    sources: list[dict] = Field(default_factory=list)


class SynthesizeInput(BaseModel):
    query: str
    session_id: str = ""
    conversation_history: list[dict] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)


class SynthesizeOutput(BaseModel):
    response: str = Field(min_length=1)
    status: str = Field(default="complete", pattern=r"^(complete|error)$")
```

**`backend/contracts/planner.py`**:

```python
from pydantic import BaseModel, Field


class GatherContextInput(BaseModel):
    run_id: str
    student_interests: list[str] = Field(default_factory=list)
    program_slug: str = ""
    completed_codes: list[str] = Field(default_factory=list)
    target_semesters: int = Field(default=4, ge=1, le=12)
    pdf_bytes: bytes | None = None
    pdf_filename: str = ""


class GatherContextOutput(BaseModel):
    guide_pages: list[dict] = Field(default_factory=list)
    program_requirements: dict = Field(default_factory=dict)
    candidate_courses: list[dict] = Field(default_factory=list)
    work_dir: str = ""


class PlanAgentInput(BaseModel):
    run_id: str
    student_interests: list[str] = Field(default_factory=list)
    target_semesters: int = 4
    candidate_courses: list[dict] = Field(default_factory=list)
    program_requirements: dict = Field(default_factory=dict)
    guide_pages: list[dict] = Field(default_factory=list)
    work_dir: str = ""


class PlanAgentOutput(BaseModel):
    plan_markdown: str = Field(min_length=1)
    plan_semesters: list[dict] = Field(default_factory=list)
    status: str = "complete"
```

### 4.3 Build the Contract Registry

**`backend/lib/contracts.py`**:

```python
from stroma import ContractRegistry, NodeContract

from backend.contracts.ingest import (
    PrecheckInput,
    PrecheckOutput,
    ScrapeInput,
    ScrapeOutput,
    ResolveInput,
    ResolveOutput,
    EmbedInput,
    EmbedOutput,
)
from backend.contracts.retrieval import (
    RetrievalInput,
    KeywordOutput,
    SemanticOutput,
    GraphOutput,
    StructuredOutput,
    FusionInput,
    FusionOutput,
)
from backend.contracts.synthesis import (
    ContextPackInput,
    ContextPackOutput,
    SynthesizeInput,
    SynthesizeOutput,
)
from backend.contracts.planner import (
    GatherContextInput,
    GatherContextOutput,
    PlanAgentInput,
    PlanAgentOutput,
)


def build_registry() -> ContractRegistry:
    """Build and return a ContractRegistry with all McGill node contracts."""
    registry = ContractRegistry()

    # Ingest pipeline
    registry.register(NodeContract(node_id="precheck", input_schema=PrecheckInput, output_schema=PrecheckOutput))
    registry.register(NodeContract(node_id="scrape", input_schema=ScrapeInput, output_schema=ScrapeOutput))
    registry.register(NodeContract(node_id="resolve", input_schema=ResolveInput, output_schema=ResolveOutput))
    registry.register(NodeContract(node_id="embed", input_schema=EmbedInput, output_schema=EmbedOutput))

    # Retrieval pipeline
    registry.register(NodeContract(node_id="keyword", input_schema=RetrievalInput, output_schema=KeywordOutput))
    registry.register(NodeContract(node_id="semantic", input_schema=RetrievalInput, output_schema=SemanticOutput))
    registry.register(NodeContract(node_id="graph", input_schema=RetrievalInput, output_schema=GraphOutput))
    registry.register(NodeContract(node_id="structured", input_schema=RetrievalInput, output_schema=StructuredOutput))
    registry.register(NodeContract(node_id="fusion", input_schema=FusionInput, output_schema=FusionOutput))

    # Synthesis pipeline
    registry.register(NodeContract(node_id="context_pack", input_schema=ContextPackInput, output_schema=ContextPackOutput))
    registry.register(NodeContract(node_id="synthesize", input_schema=SynthesizeInput, output_schema=SynthesizeOutput))

    # Planner pipeline
    registry.register(NodeContract(node_id="gather_context", input_schema=GatherContextInput, output_schema=GatherContextOutput))
    registry.register(NodeContract(node_id="plan_agent", input_schema=PlanAgentInput, output_schema=PlanAgentOutput))

    return registry
```

### 4.4 Define Failure Classifiers

**`backend/lib/classifiers.py`**:

```python
import logging

from stroma import FailureClass, NodeContext

logger = logging.getLogger(__name__)


def playwright_classifier(exc: Exception, ctx: NodeContext) -> FailureClass | None:
    """Classify Playwright browser errors.

    Timeouts and connection issues during scraping are recoverable —
    the McGill website may be temporarily slow. Page-not-found or
    selector errors are terminal.
    """
    exc_type = type(exc).__name__
    msg = str(exc).lower()

    if exc_type == "TimeoutError" or "timeout" in msg:
        return FailureClass.RECOVERABLE
    if "net::err_connection" in msg or "disconnected" in msg:
        return FailureClass.RECOVERABLE
    if "navigation failed" in msg:
        return FailureClass.RECOVERABLE
    if "selector" in msg or "not found" in msg:
        return FailureClass.TERMINAL
    return None


def anthropic_classifier(exc: Exception, ctx: NodeContext) -> FailureClass | None:
    """Classify Anthropic API errors.

    - 529 (overloaded): recoverable with longer backoff
    - 429 (rate limit): recoverable
    - 400 (bad request): terminal — broken prompt, won't fix on retry
    - 401/403 (auth): terminal
    """
    exc_type = type(exc).__name__
    msg = str(exc).lower()

    if exc_type in ("OverloadedError", "RateLimitError"):
        return FailureClass.RECOVERABLE
    if "overloaded" in msg or "529" in msg:
        return FailureClass.RECOVERABLE
    if "rate limit" in msg or "429" in msg:
        return FailureClass.RECOVERABLE
    if "bad request" in msg or "400" in msg:
        return FailureClass.TERMINAL
    if "unauthorized" in msg or "forbidden" in msg:
        return FailureClass.TERMINAL
    return None


def voyage_classifier(exc: Exception, ctx: NodeContext) -> FailureClass | None:
    """Classify Voyage AI embedding errors.

    Rate limits and timeouts are recoverable. Invalid input
    (e.g., text too long) is terminal.
    """
    msg = str(exc).lower()

    if "rate limit" in msg or "429" in msg:
        return FailureClass.RECOVERABLE
    if "timeout" in msg:
        return FailureClass.RECOVERABLE
    if "too long" in msg or "invalid" in msg:
        return FailureClass.TERMINAL
    return None


def neo4j_classifier(exc: Exception, ctx: NodeContext) -> FailureClass | None:
    """Classify Neo4j driver errors.

    Connection issues are recoverable. Syntax errors in Cypher
    queries are terminal.
    """
    exc_type = type(exc).__name__
    msg = str(exc).lower()

    if "serviceunvailable" in exc_type.lower() or "connection" in msg:
        return FailureClass.RECOVERABLE
    if "syntax" in msg or "cypher" in msg:
        return FailureClass.TERMINAL
    return None


ALL_CLASSIFIERS = [
    playwright_classifier,
    anthropic_classifier,
    voyage_classifier,
    neo4j_classifier,
]
```

At the end of Phase 1, the project has contract schemas and classifiers defined but no runtime behavior has changed.

---

## 5. Phase 2 — Wrap the Ingest Pipeline

The ingest pipeline is the highest-value target: it's long-running (minutes to hours), hits the flakiest external service (McGill's website via Playwright), and has no retry or resume capability today.

### 5.1 Current Ingest Architecture

```
precheck_node ──► scrape_node ──► resolve_node ──► embed_node
     │                 │                │               │
  Check which     Playwright       Fuzzy match      Voyage AI
  depts need      browser →        prereqs →        embeddings →
  processing      PostgreSQL       Neo4j graph      pgvector
```

**Current nodes** (`backend/workflows/ingest/nodes.py`) catch all exceptions and return error dicts:

```python
async def scrape_node(state: IngestState) -> IngestState:
    try:
        # ... Playwright scraping + PostgreSQL insert ...
        return {"courses_scraped": len(courses), "scrape_status": "complete"}
    except Exception as e:
        return {"scrape_status": "error", "errors": [f"scrape: {e}\n{traceback.format_exc()}"]}
```

This swallows errors. Stroma replaces this with structured failure handling.

### 5.2 Decorate Ingest Nodes

Add `@stroma_langgraph_node` decorators to each node function. The decorator attaches contract metadata so `LangGraphAdapter` can discover and validate them.

**`backend/workflows/ingest/nodes.py`** (modified):

```python
from __future__ import annotations

import logging
import traceback
from pathlib import Path

from stroma.adapters.langgraph import stroma_langgraph_node
from stroma import NodeContract

from backend.contracts.ingest import (
    PrecheckInput,
    PrecheckOutput,
    ScrapeInput,
    ScrapeOutput,
    ResolveInput,
    ResolveOutput,
    EmbedInput,
    EmbedOutput,
)
from backend.workflows.ingest.state import IngestState

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


@stroma_langgraph_node(
    "precheck",
    NodeContract(node_id="precheck", input_schema=PrecheckInput, output_schema=PrecheckOutput),
)
async def precheck_node(state: IngestState) -> IngestState:
    """Determine which departments need processing by checking for existing embeddings."""
    from backend.db.postgres import get_pool
    from backend.services.scraping.faculties import ALL_FACULTIES, get_active_faculties

    force = state.get("force", False)
    faculty_filter = state.get("faculty_filter")
    dept_filter = state.get("dept_filter")

    if dept_filter:
        target_depts = [d.upper() for d in dept_filter]
    elif faculty_filter:
        active = get_active_faculties(faculty_filter)
        if not active:
            raise ValueError(f"No faculties matched filter {faculty_filter!r}")
        target_depts = [p for _, _, prefixes in active for p in prefixes]
    else:
        target_depts = [p for _, _, prefixes in ALL_FACULTIES for p in prefixes]

    if force:
        logger.info("Force flag set — processing all %d departments", len(target_depts))
        return {"skipped_depts": [], "active_depts": target_depts}

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT DISTINCT c.dept FROM courses c
               JOIN course_chunks cc ON cc.course_id = c.id
               WHERE c.dept = ANY($1)""",
            target_depts,
        )
    completed = {r["dept"] for r in rows}
    active = [d for d in target_depts if d not in completed]
    skipped = [d for d in target_depts if d in completed]

    if skipped:
        logger.info("Skipping %d already-processed departments", len(skipped))
    if active:
        logger.info("Processing %d departments", len(active))

    return {"skipped_depts": skipped, "active_depts": active}


@stroma_langgraph_node(
    "scrape",
    NodeContract(node_id="scrape", input_schema=ScrapeInput, output_schema=ScrapeOutput),
)
async def scrape_node(state: IngestState) -> IngestState:
    """Scrape course catalogue pages via Playwright and insert into PostgreSQL.

    Exceptions propagate to Stroma's failure handler instead of being swallowed.
    Playwright timeouts are classified RECOVERABLE and retried automatically.
    """
    from backend.services.scraping.catalogue import run as run_scrape
    from backend.db.postgres import get_pool

    active_depts = state.get("active_depts")
    courses = await run_scrape(
        faculty_filter=state.get("faculty_filter") if not active_depts else None,
        dept_filter=active_depts or state.get("dept_filter"),
        max_course_pages=state.get("max_course_pages"),
        max_program_pages=state.get("max_program_pages"),
    )

    pool = await get_pool()
    async with pool.acquire() as conn:
        for c in courses:
            await conn.execute(
                """INSERT INTO courses (code, slug, title, dept, number, credits,
                       faculty, terms, description, prerequisites_raw,
                       restrictions_raw, notes_raw, url, name_variants)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                   ON CONFLICT (code) DO UPDATE SET
                       title = EXCLUDED.title,
                       description = EXCLUDED.description,
                       prerequisites_raw = EXCLUDED.prerequisites_raw,
                       restrictions_raw = EXCLUDED.restrictions_raw,
                       terms = EXCLUDED.terms,
                       updated_at = now()""",
                c.code, c.slug, c.title, c.dept, c.number, c.credits,
                c.faculty, c.terms, c.description, c.prerequisites_raw,
                c.restrictions_raw, c.notes_raw, c.url, c.name_variants,
            )

    return {"courses_scraped": len(courses), "scrape_status": "complete"}


@stroma_langgraph_node(
    "resolve",
    NodeContract(node_id="resolve", input_schema=ResolveInput, output_schema=ResolveOutput),
)
async def resolve_node(state: IngestState) -> IngestState:
    """Entity resolution and Neo4j graph build."""
    from backend.db.postgres import get_pool
    from backend.models.course import CourseCreate
    from backend.services.resolution.prerequisites import parse_prerequisites
    from backend.services.resolution.entity_graph import (
        build_faculty_nodes,
        build_course_nodes,
        build_relationships,
    )

    pool = await get_pool()
    active_depts = state.get("active_depts")

    async with pool.acquire() as conn:
        if active_depts:
            rows = await conn.fetch(
                "SELECT * FROM courses WHERE dept = ANY($1)", active_depts
            )
        else:
            rows = await conn.fetch("SELECT * FROM courses")

    courses = [
        CourseCreate(
            code=r["code"], slug=r["slug"], title=r["title"], dept=r["dept"],
            number=r["number"], credits=r["credits"], faculty=r["faculty"],
            faculties=[], terms=r["terms"] or [], description=r["description"] or "",
            prerequisites_raw=r["prerequisites_raw"] or "",
            restrictions_raw=r["restrictions_raw"] or "",
            notes_raw=r["notes_raw"] or "", url=r["url"] or "",
            name_variants=r["name_variants"] or [],
        )
        for r in rows
    ]

    known_codes = {c.code for c in courses}
    await build_faculty_nodes()
    entity_count = await build_course_nodes(courses)

    all_refs = []
    for c in courses:
        refs = parse_prerequisites(c.code, c.prerequisites_raw, c.restrictions_raw, known_codes)
        all_refs.extend(refs)

    rel_count = await build_relationships(all_refs)

    return {
        "entities_created": entity_count,
        "relationships_created": rel_count,
        "resolve_status": "complete",
    }


@stroma_langgraph_node(
    "embed",
    NodeContract(node_id="embed", input_schema=EmbedInput, output_schema=EmbedOutput),
)
async def embed_node(state: IngestState) -> IngestState:
    """Generate Voyage AI embeddings and store in pgvector.

    Voyage rate limit errors are classified RECOVERABLE and retried
    with backoff.
    """
    from backend.db.postgres import get_pool
    from backend.services.embedding.chunker import chunk_course, chunk_program_page
    from backend.services.embedding.voyage import embed_texts
    from backend.services.embedding.vector_store import (
        insert_chunks,
        insert_program_chunks,
        create_ivfflat_index,
    )

    pool = await get_pool()
    active_depts = state.get("active_depts")

    async with pool.acquire() as conn:
        if active_depts:
            rows = await conn.fetch(
                """SELECT id, code, title, description, prerequisites_raw,
                          restrictions_raw, notes_raw, dept, faculty
                   FROM courses WHERE dept = ANY($1)""",
                active_depts,
            )
        else:
            rows = await conn.fetch(
                """SELECT id, code, title, description, prerequisites_raw,
                          restrictions_raw, notes_raw, dept, faculty
                   FROM courses"""
            )

    total_course_chunks = 0
    batch_texts: list[str] = []
    batch_meta: list[tuple[int, int]] = []

    for r in rows:
        chunks = chunk_course(
            code=r["code"], title=r["title"], description=r["description"] or "",
            prerequisites_raw=r["prerequisites_raw"] or "",
            restrictions_raw=r["restrictions_raw"] or "",
            notes_raw=r["notes_raw"] or "", dept=r["dept"] or "",
            faculty=r["faculty"] or "",
        )
        batch_meta.append((r["id"], len(batch_texts)))
        batch_texts.extend(chunks)

    if batch_texts:
        all_embeddings = embed_texts(batch_texts)
        for i, (course_id, start_idx) in enumerate(batch_meta):
            end_idx = batch_meta[i + 1][1] if i + 1 < len(batch_meta) else len(batch_texts)
            course_chunks = batch_texts[start_idx:end_idx]
            course_embs = all_embeddings[start_idx:end_idx]
            total_course_chunks += await insert_chunks(course_id, course_chunks, course_embs)

    # Program page chunks
    async with pool.acquire() as conn:
        prog_rows = await conn.fetch(
            "SELECT id, title, content, faculty_slug FROM program_pages"
        )

    total_prog_chunks = 0
    prog_texts: list[str] = []
    prog_meta: list[tuple[int, int]] = []

    for r in prog_rows:
        chunks = chunk_program_page(
            title=r["title"] or "", content=r["content"] or "",
            faculty_slug=r["faculty_slug"] or "",
        )
        if chunks:
            prog_meta.append((r["id"], len(prog_texts)))
            prog_texts.extend(chunks)

    if prog_texts:
        prog_embeddings = embed_texts(prog_texts)
        for i, (page_id, start_idx) in enumerate(prog_meta):
            end_idx = prog_meta[i + 1][1] if i + 1 < len(prog_meta) else len(prog_texts)
            page_chunks = prog_texts[start_idx:end_idx]
            page_embs = prog_embeddings[start_idx:end_idx]
            total_prog_chunks += await insert_program_chunks(page_id, page_chunks, page_embs)

    await create_ivfflat_index()

    return {
        "chunks_created": total_course_chunks + total_prog_chunks,
        "embed_status": "complete",
    }
```

**Key changes from the original nodes:**
- `@stroma_langgraph_node` decorator added to each function
- `try/except` blocks removed — exceptions propagate to Stroma's failure handler
- Error dicts (`{"scrape_status": "error", "errors": [...]}`) replaced with raised exceptions
- Contract schemas enforce that each node returns the expected shape

### 5.3 Modify the Ingest Orchestrator

**`backend/workflows/ingest/graph.py`** (modified):

```python
from __future__ import annotations

import uuid

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from stroma import FailureClass, FailurePolicy, NodeHooks, RunConfig
from stroma.adapters.langgraph import LangGraphAdapter
from stroma.checkpoint import RedisStore, CheckpointManager

from backend.lib.orchestrator import WorkflowOrchestrator
from backend.lib.registry import registry, WorkflowConfig
from backend.lib.contracts import build_registry
from backend.lib.classifiers import ALL_CLASSIFIERS
from backend.config import settings
from backend.workflows.ingest.state import IngestState
from backend.workflows.ingest.nodes import (
    precheck_node,
    scrape_node,
    resolve_node,
    embed_node,
)

# Stroma contract registry (shared across runs)
_stroma_registry = build_registry()

# Retry policies tuned per failure class
INGEST_POLICIES = {
    FailureClass.RECOVERABLE: FailurePolicy(max_retries=3, backoff_seconds=2.0),
    FailureClass.TERMINAL: FailurePolicy(max_retries=0, backoff_seconds=0),
    FailureClass.AMBIGUOUS: FailurePolicy(max_retries=1, backoff_seconds=1.0),
}

# Per-node overrides — embed node gets more retries for Voyage rate limits
INGEST_NODE_POLICIES = {
    "embed": {
        FailureClass.RECOVERABLE: FailurePolicy(max_retries=5, backoff_seconds=1.0),
    },
    "scrape": {
        FailureClass.RECOVERABLE: FailurePolicy(max_retries=3, backoff_seconds=3.0),
    },
}


def _after_precheck(state: IngestState) -> str:
    if state.get("scrape_status") == "error":
        return END
    if not state.get("active_depts"):
        return END
    return "scrape"


def _after_scrape(state: IngestState) -> str:
    if state.get("scrape_status") == "error":
        return END
    return "resolve"


def _after_resolve(state: IngestState) -> str:
    if state.get("resolve_status") == "error":
        return END
    return "embed"


def _after_embed(state: IngestState) -> str:
    return END


class IngestOrchestrator(WorkflowOrchestrator):
    def build_graph(self) -> CompiledStateGraph:
        graph = StateGraph(IngestState)  # type: ignore[arg-type]

        graph.add_node("precheck", precheck_node)
        graph.add_node("scrape", scrape_node)
        graph.add_node("resolve", resolve_node)
        graph.add_node("embed", embed_node)

        graph.set_entry_point("precheck")
        graph.add_conditional_edges("precheck", _after_precheck)
        graph.add_conditional_edges("scrape", _after_scrape)
        graph.add_conditional_edges("resolve", _after_resolve)
        graph.add_conditional_edges("embed", _after_embed)

        compiled = graph.compile()

        # Wrap with Stroma — contract validation on every node boundary
        adapter = LangGraphAdapter(_stroma_registry)
        adapter.wrap(compiled)

        return compiled

    def build_initial_state(
        self,
        faculty_filter=None,
        dept_filter=None,
        max_course_pages=None,
        max_program_pages=None,
        force=False,
        **kwargs,
    ) -> IngestState:
        return IngestState(
            run_id=str(uuid.uuid4()),
            errors=[],
            status="pending",
            faculty_filter=faculty_filter,
            dept_filter=dept_filter,
            max_course_pages=max_course_pages,
            max_program_pages=max_program_pages,
            force=force,
        )


registry.register(
    WorkflowConfig(
        name="ingest",
        orchestrator_class=IngestOrchestrator,
        description="Scrape -> resolve -> chunk -> embed (with Stroma reliability)",
    )
)
```

### 5.4 Checkpoint + Resume Support

To enable resume-from-checkpoint, the `IngestOrchestrator` can expose a `run_with_resume` method that uses `StromaRunner` directly for sequential execution outside of LangGraph:

**`backend/workflows/ingest/runner.py`** (new file):

```python
from __future__ import annotations

import logging

from stroma import StromaRunner, FailureClass, FailurePolicy, NodeHooks, RunConfig
from stroma.checkpoint import RedisStore, CheckpointManager

from backend.config import settings
from backend.lib.contracts import build_registry
from backend.lib.classifiers import ALL_CLASSIFIERS
from backend.contracts.ingest import PrecheckInput
from backend.workflows.ingest.nodes import (
    precheck_node,
    scrape_node,
    resolve_node,
    embed_node,
)

logger = logging.getLogger(__name__)

REDIS_URL = "redis://redis:6379/0"


async def run_ingest_with_stroma(
    faculty_filter: list[str] | None = None,
    dept_filter: list[str] | None = None,
    max_course_pages: int | None = None,
    max_program_pages: int | None = None,
    force: bool = False,
    resume_from: str | None = None,
    run_id: str | None = None,
    on_node_start=None,
    on_node_success=None,
    on_node_failure=None,
):
    """Run the ingest pipeline with full Stroma reliability.

    **resume_from** and **run_id** enable checkpoint resumption. To resume
    a failed run, pass the original `run_id` and the node to restart from
    (e.g., `resume_from="embed"`).

    **on_node_start**, **on_node_success**, **on_node_failure** are optional
    async callbacks for SSE streaming integration.
    """
    runner = (
        StromaRunner.quick()
        .with_redis(REDIS_URL, ttl_seconds=7200)
        .with_classifiers(ALL_CLASSIFIERS)
        .with_policy_map({
            FailureClass.RECOVERABLE: FailurePolicy(max_retries=3, backoff_seconds=2.0),
            FailureClass.TERMINAL: FailurePolicy(max_retries=0, backoff_seconds=0),
            FailureClass.AMBIGUOUS: FailurePolicy(max_retries=1, backoff_seconds=1.0),
        })
        .with_node_policies({
            "embed": {
                FailureClass.RECOVERABLE: FailurePolicy(max_retries=5, backoff_seconds=1.0),
            },
            "scrape": {
                FailureClass.RECOVERABLE: FailurePolicy(max_retries=3, backoff_seconds=3.0),
            },
        })
        .with_node_timeouts({
            "scrape": 300_000,   # 5 minutes per scrape attempt
            "embed": 600_000,    # 10 minutes for embedding large batches
        })
        .with_hooks(NodeHooks(
            on_node_start=on_node_start,
            on_node_success=on_node_success,
            on_node_failure=on_node_failure,
        ))
    )

    # Override run_id and resume_from if provided
    if run_id:
        runner.config = runner.config.model_copy(update={"run_id": run_id})
    if resume_from:
        runner.config = runner.config.model_copy(update={"resume_from": resume_from})

    initial_state = PrecheckInput(
        run_id=runner.config.run_id,
        faculty_filter=faculty_filter,
        dept_filter=dept_filter,
        force=force,
    )

    result = await runner.run(
        [precheck_node, scrape_node, resolve_node, embed_node],
        initial_state,
    )

    logger.info(
        "Ingest pipeline %s: status=%s, cost=$%.4f, tokens=%d",
        result.run_id,
        result.status,
        result.total_cost_usd,
        result.total_tokens,
    )

    return result
```

**Usage — fresh run:**

```python
result = await run_ingest_with_stroma(faculty_filter=["science"])
# result.status == RunStatus.COMPLETED
```

**Usage — resume after failure at embed:**

```python
result = await run_ingest_with_stroma(
    faculty_filter=["science"],
    run_id="original-run-uuid",       # same run_id as the failed run
    resume_from="embed",              # skip precheck, scrape, resolve
)
# result.status == RunStatus.RESUMED
```

---

## 6. Phase 3 — Wrap Retrieval + Synthesis Pipelines

### 6.1 Decorate Retrieval Nodes

**`backend/workflows/retrieval/nodes.py`** (modified — key changes shown):

```python
from __future__ import annotations

import asyncio
import logging
import re
import traceback

from stroma.adapters.langgraph import stroma_langgraph_node
from stroma import NodeContract

from backend.contracts.retrieval import (
    RetrievalInput,
    KeywordOutput,
    SemanticOutput,
    GraphOutput,
    StructuredOutput,
    FusionInput,
    FusionOutput,
)
from backend.workflows.retrieval.state import RetrievalState

logger = logging.getLogger("backend.workflows.retrieval")


@stroma_langgraph_node(
    "keyword",
    NodeContract(node_id="keyword", input_schema=RetrievalInput, output_schema=KeywordOutput),
)
async def keyword_node(state: RetrievalState) -> RetrievalState:
    """Full-text keyword search on courses."""
    from backend.services.embedding.retrieval import keyword_search

    results = await keyword_search(state["query"], top_k=state.get("top_k", 10))
    return {"keyword_results": results}


@stroma_langgraph_node(
    "semantic",
    NodeContract(node_id="semantic", input_schema=RetrievalInput, output_schema=SemanticOutput),
)
async def semantic_node(state: RetrievalState) -> RetrievalState:
    """Dense vector semantic search — embeds query once via Voyage AI,
    searches both course chunks and program pages in parallel.
    """
    from backend.services.embedding.voyage import embed_query
    from backend.services.embedding.vector_store import search_similar, search_similar_programs

    query_emb = embed_query(state["query"])
    top_k = state.get("top_k", 10)
    course_results, program_results = await asyncio.gather(
        search_similar(query_emb, top_k),
        search_similar_programs(query_emb, 5),
    )
    return {"semantic_results": course_results, "program_results": program_results}


@stroma_langgraph_node(
    "graph",
    NodeContract(node_id="graph", input_schema=RetrievalInput, output_schema=GraphOutput),
)
async def graph_node(state: RetrievalState) -> RetrievalState:
    """Neo4j prerequisite query if course codes detected in query."""
    codes = re.findall(r"\b([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)\b", state["query"].upper())
    if not codes:
        return {"graph_context": ""}

    from backend.db.neo4j import run_query

    code = f"{codes[0][0]} {codes[0][1]}"
    prereqs = await run_query(
        """MATCH (c:Course {code: $code})-[:PREREQUISITE_OF]->(p:Course)
           RETURN p.code AS code, p.title AS title""",
        {"code": code},
    )
    if prereqs:
        ctx = f"Prerequisites for {code}: " + ", ".join(
            f"{r['code']} ({r['title']})" for r in prereqs
        )
        return {"graph_context": ctx}
    return {"graph_context": ""}


@stroma_langgraph_node(
    "structured",
    NodeContract(node_id="structured", input_schema=RetrievalInput, output_schema=StructuredOutput),
)
async def structured_node(state: RetrievalState) -> RetrievalState:
    """Text-to-SQL: Claude Haiku generates a read-only SQL query, executes it, returns results.

    Anthropic API errors are classified by the anthropic_classifier and retried
    as appropriate.
    """
    import anthropic
    from backend.config import settings
    from backend.db.postgres import get_pool

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=(
            "You are a PostgreSQL query generator for a McGill University course database.\n"
            f"{_DB_SCHEMA}\n"
            "Generate a single read-only SELECT query that answers the user's question. "
            "Return ONLY the SQL — no explanation, no markdown, no backticks. "
            "If the question cannot be answered with SQL, return exactly: SKIP"
        ),
        messages=[{"role": "user", "content": state["query"]}],
    )

    sql = response.content[0].text.strip().rstrip(";")
    if sql == "SKIP" or not sql.upper().startswith("SELECT"):
        return {"structured_context": ""}

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            await conn.execute("SET LOCAL statement_timeout = '5s'")
            rows = await conn.fetch(sql)

    if not rows:
        return {"structured_context": f"SQL query returned no results.\nQuery: {sql}"}

    columns = list(rows[0].keys())
    lines = [f"SQL results ({len(rows)} rows):"]
    lines.append(" | ".join(columns))
    lines.append("-" * 40)
    for r in rows[:25]:
        lines.append(" | ".join(str(r[c]) for c in columns))
    if len(rows) > 25:
        lines.append(f"... and {len(rows) - 25} more rows")

    return {"structured_context": "\n".join(lines)}


@stroma_langgraph_node(
    "fusion",
    NodeContract(node_id="fusion", input_schema=FusionInput, output_schema=FusionOutput),
)
async def fusion_node(state: RetrievalState) -> RetrievalState:
    """Reciprocal rank fusion across keyword + semantic results."""
    from backend.services.embedding.retrieval import reciprocal_rank_fusion

    fused = reciprocal_rank_fusion(
        state.get("keyword_results", []),
        state.get("semantic_results", []),
        top_n=state.get("top_k", 10),
    )
    return {"fused_results": fused, "status": "complete"}
```

### 6.2 Wrap the Retrieval Graph

**`backend/workflows/retrieval/graph.py`** (modified):

```python
from __future__ import annotations

import asyncio
import uuid

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from stroma.adapters.langgraph import LangGraphAdapter

from backend.lib.orchestrator import WorkflowOrchestrator
from backend.lib.registry import registry, WorkflowConfig
from backend.lib.contracts import build_registry
from backend.workflows.retrieval.state import RetrievalState
from backend.workflows.retrieval.nodes import (
    keyword_node,
    semantic_node,
    graph_node,
    structured_node,
    fusion_node,
)

_stroma_registry = build_registry()


async def parallel_retrieval_node(state: RetrievalState) -> RetrievalState:
    """Run keyword, semantic, graph, and structured retrieval in parallel.

    Each branch is individually decorated with @stroma_langgraph_node, so
    contract validation runs per branch inside the gather.
    """
    results = await asyncio.gather(
        keyword_node(state),
        semantic_node(state),
        graph_node(state),
        structured_node(state),
        return_exceptions=True,
    )

    merged: dict = {}
    errors: list[str] = []
    for r in results:
        if isinstance(r, Exception):
            errors.append(str(r))
        elif isinstance(r, dict):
            errors.extend(r.pop("errors", []))
            merged.update(r)

    if errors:
        merged["errors"] = errors
    return merged  # type: ignore[return-value]


class RetrievalOrchestrator(WorkflowOrchestrator):
    def build_graph(self) -> CompiledStateGraph:
        graph = StateGraph(RetrievalState)  # type: ignore[arg-type]

        graph.add_node("retrieve", parallel_retrieval_node)
        graph.add_node("fusion", fusion_node)

        graph.set_entry_point("retrieve")
        graph.add_edge("retrieve", "fusion")
        graph.add_edge("fusion", END)

        compiled = graph.compile()

        # Wrap fusion node with Stroma validation
        adapter = LangGraphAdapter(_stroma_registry)
        adapter.wrap(compiled)

        return compiled

    def build_initial_state(self, query="", top_k=10, mode="hybrid", **kwargs) -> RetrievalState:
        return RetrievalState(
            run_id=str(uuid.uuid4()),
            errors=[],
            status="pending",
            query=query,
            top_k=top_k,
            mode=mode,
            keyword_results=[],
            semantic_results=[],
            program_results=[],
            graph_context="",
            structured_context="",
            fused_results=[],
        )


registry.register(
    WorkflowConfig(
        name="retrieval",
        orchestrator_class=RetrievalOrchestrator,
        description="Hybrid dense + sparse retrieval with RRF fusion (Stroma-validated)",
    )
)
```

### 6.3 Wrap Synthesis Nodes with Cost Tracking

The synthesis pipeline calls Claude directly. By returning a cost tuple `(dict, input_tokens, output_tokens, model)`, Stroma tracks per-node costs automatically.

**`backend/workflows/synthesis/nodes.py`** (modified):

```python
from __future__ import annotations

from stroma.adapters.langgraph import stroma_langgraph_node
from stroma import NodeContract

from backend.contracts.synthesis import (
    ContextPackInput,
    ContextPackOutput,
    SynthesizeInput,
    SynthesizeOutput,
)
from backend.workflows.synthesis.state import SynthesisState

SYSTEM_PROMPT = (
    "You are a McGill University course advisor assistant. "
    "Help students find courses, understand prerequisites, and plan their studies. "
    "Use the provided course data to answer accurately. "
    "When SQL results are provided in the context, treat them as authoritative data from the database "
    "and use them directly to answer the question — do not say you lack information. "
    "Be concise and cite specific course codes when relevant."
)


@stroma_langgraph_node(
    "context_pack",
    NodeContract(node_id="context_pack", input_schema=ContextPackInput, output_schema=ContextPackOutput),
)
async def context_pack_node(state: SynthesisState) -> SynthesisState:
    """Assemble retrieval context into a Claude-ready string."""
    parts: list[str] = []

    for r in state.get("retrieval_context", []):
        parts.append(f"{r.get('code', '')}: {r.get('title', '')}\n{r.get('description', '')}")

    graph_ctx = state.get("graph_context", "")
    if graph_ctx:
        parts.append(graph_ctx)

    structured_ctx = state.get("structured_context", "")
    if structured_ctx:
        parts.insert(0, structured_ctx)

    for r in state.get("program_context", []):
        title = r.get("title", r.get("faculty_slug", ""))
        text = r.get("text", "")
        if text:
            parts.append(f"[{title}]\n{text}")

    context_text = "\n---\n".join(parts)
    if len(context_text) > 8000:
        context_text = context_text[:8000] + "\n... (trimmed)"

    return {"sources": [{"context_text": context_text}]}


@stroma_langgraph_node(
    "synthesize",
    NodeContract(node_id="synthesize", input_schema=SynthesizeInput, output_schema=SynthesizeOutput),
)
async def synthesize_node(state: SynthesisState) -> SynthesisState:
    """Call Anthropic API with system prompt + packed context + conversation history.

    Returns a cost tuple so Stroma can track token usage and USD cost
    per synthesis call.
    """
    from backend.config import settings
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    context_text = ""
    for s in state.get("sources", []):
        if "context_text" in s:
            context_text = s["context_text"]
            break

    messages = [
        {"role": "user", "content": f"Context:\n{context_text}\n\nQuestion: {state['query']}"}
    ]

    history = state.get("conversation_history", [])[-6:]
    if len(history) > 1:
        messages = history[:-1] + messages

    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    answer = response.content[0].text
    return {"response": answer, "status": "complete"}
```

### 6.4 Surface Cost in SSE Stream

After synthesis completes, the `ExecutionResult` contains cost info that can be streamed to the frontend:

```python
# In backend/api/routes/chat.py — inside _run_qa_pipeline

retrieval_result = await retrieval_orchestrator.run(query=question, top_k=10, mode="hybrid")
synthesis_result = await synthesis_orchestrator.run(
    query=question,
    session_id=session_id,
    conversation_history=messages,
    retrieval_context=retrieval_result.get("fused_results", []),
    program_context=retrieval_result.get("program_results", []),
    graph_context=retrieval_result.get("graph_context", ""),
    structured_context=retrieval_result.get("structured_context", ""),
)

# New SSE event with cost info (from Stroma execution result)
await event_queue.put(_sse("cost", {
    "total_cost_usd": synthesis_result.total_cost_usd,
    "total_tokens": synthesis_result.total_tokens,
}))
```

---

## 7. Phase 4 — Budget Enforcement + Planner Safety

The planner workflow uses Claude Agent SDK with tool loops — the most expensive and least predictable workflow. Budget caps prevent runaway costs.

### 7.1 Planner with Budget + Timeout

**`backend/workflows/planner/runner.py`** (new file):

```python
from __future__ import annotations

import logging

from stroma import StromaRunner, FailureClass, FailurePolicy, ExecutionBudget, NodeHooks

from backend.lib.contracts import build_registry
from backend.lib.classifiers import ALL_CLASSIFIERS
from backend.contracts.planner import GatherContextInput

from backend.workflows.planner.nodes import gather_context_node, plan_agent_node

logger = logging.getLogger(__name__)

REDIS_URL = "redis://redis:6379/0"


async def run_planner_with_stroma(
    student_interests: list[str],
    program_slug: str = "",
    completed_codes: list[str] | None = None,
    target_semesters: int = 4,
    pdf_bytes: bytes | None = None,
    pdf_filename: str = "",
    on_node_start=None,
    on_node_success=None,
    on_node_failure=None,
):
    """Run the curriculum planner with Stroma budget enforcement.

    The plan_agent node gets a 120-second timeout and the overall run
    is capped at $5.00 USD and 200,000 tokens to prevent runaway
    agentic loops.
    """
    runner = (
        StromaRunner.quick()
        .with_redis(REDIS_URL, ttl_seconds=3600)
        .with_classifiers(ALL_CLASSIFIERS)
        .with_budget(
            tokens=200_000,
            cost_usd=5.0,
            latency_ms=300_000,  # 5-minute total budget
        )
        .with_policy_map({
            FailureClass.RECOVERABLE: FailurePolicy(max_retries=2, backoff_seconds=2.0),
            FailureClass.TERMINAL: FailurePolicy(max_retries=0, backoff_seconds=0),
            FailureClass.AMBIGUOUS: FailurePolicy(max_retries=1, backoff_seconds=1.0),
        })
        .with_node_timeouts({
            "gather_context": 60_000,   # 60 seconds for context gathering
            "plan_agent": 120_000,      # 120 seconds for agent tool loops
        })
        .with_hooks(NodeHooks(
            on_node_start=on_node_start,
            on_node_success=on_node_success,
            on_node_failure=on_node_failure,
        ))
    )

    initial_state = GatherContextInput(
        run_id=runner.config.run_id,
        student_interests=student_interests,
        program_slug=program_slug,
        completed_codes=completed_codes or [],
        target_semesters=target_semesters,
        pdf_bytes=pdf_bytes,
        pdf_filename=pdf_filename,
    )

    result = await runner.run(
        [gather_context_node, plan_agent_node],
        initial_state,
    )

    logger.info(
        "Planner %s: status=%s, cost=$%.4f, tokens=%d",
        result.run_id,
        result.status,
        result.total_cost_usd,
        result.total_tokens,
    )

    return result
```

### 7.2 Budget Status in SSE Stream

When the planner hits a budget limit, Stroma raises `BudgetExceeded` (classified `RECOVERABLE`). After retries exhaust, the run returns `RunStatus.PARTIAL`. Surface this in the SSE stream:

```python
# In backend/api/routes/chat.py — inside _run_planner_bg

from stroma import RunStatus

result = await run_planner_with_stroma(
    student_interests=interests,
    target_semesters=semesters,
    on_node_start=_planner_node_start_handler,
    on_node_success=_planner_node_success_handler,
    on_node_failure=_planner_node_failure_handler,
)

if result.status == RunStatus.PARTIAL:
    await event_queue.put(_sse("warning", {
        "message": "Planner stopped early due to budget limits.",
        "cost_usd": result.total_cost_usd,
        "tokens": result.total_tokens,
    }))
elif result.status == RunStatus.FAILED:
    # Check trace for failure details
    failures = result.trace.failures()
    failure_msg = failures[-1].failure_message if failures else "Unknown error"
    await event_queue.put(_sse("error", {"message": failure_msg}))
```

---

## 8. Phase 5 — Observability

### 8.1 Node Hooks for Structured Logging

**`backend/lib/hooks.py`**:

```python
from __future__ import annotations

import logging

from stroma import FailureClass, NodeHooks

logger = logging.getLogger("backend.stroma")


async def _on_start(run_id: str, node_id: str, input_state: dict) -> None:
    logger.info(
        "node_start",
        extra={"run_id": run_id, "node_id": node_id, "input_keys": list(input_state.keys())},
    )


async def _on_success(run_id: str, node_id: str, output_state: dict, tokens_used: int) -> None:
    logger.info(
        "node_success",
        extra={
            "run_id": run_id,
            "node_id": node_id,
            "tokens_used": tokens_used,
            "output_keys": list(output_state.keys()),
        },
    )


async def _on_failure(run_id: str, node_id: str, exc: Exception, failure_class: FailureClass) -> None:
    logger.warning(
        "node_failure",
        extra={
            "run_id": run_id,
            "node_id": node_id,
            "failure_class": failure_class.value,
            "error": str(exc),
        },
    )


default_hooks = NodeHooks(
    on_node_start=_on_start,
    on_node_success=_on_success,
    on_node_failure=_on_failure,
)
```

### 8.2 Store Traces in pipeline_runs

Replace the coarse `status` / `result` tracking in the existing `pipeline_runs` table with Stroma's full execution trace:

```python
# After a pipeline run completes, persist the trace

import json

from backend.db.postgres import get_pool


async def persist_trace(result) -> None:
    """Store the Stroma execution trace in the pipeline_runs table."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO pipeline_runs (run_id, status, result, started_at, completed_at)
               VALUES ($1, $2, $3::jsonb, now(), now())
               ON CONFLICT (run_id) DO UPDATE SET
                   status = EXCLUDED.status,
                   result = EXCLUDED.result,
                   completed_at = now()""",
            result.run_id,
            result.status.value,
            json.dumps({
                "trace": result.trace.to_json(),
                "total_cost_usd": result.total_cost_usd,
                "total_tokens": result.total_tokens,
                "failures": [
                    {
                        "node_id": e.node_id,
                        "attempt": e.attempt,
                        "failure_class": e.failure.value if e.failure else None,
                        "message": e.failure_message,
                        "duration_ms": e.duration_ms,
                    }
                    for e in result.trace.failures()
                ],
            }),
        )
```

### 8.3 Trace API Endpoint

**`backend/api/routes/pipeline.py`** (add endpoint):

```python
from fastapi import APIRouter, HTTPException

from backend.db.postgres import get_pool

router = APIRouter()


@router.get("/api/v1/pipeline/trace/{run_id}")
async def get_pipeline_trace(run_id: str):
    """Retrieve the full Stroma execution trace for a pipeline run.

    Returns per-node timing, input/output state, failure info, retry
    counts, and cost breakdown.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT run_id, status, result, started_at, completed_at FROM pipeline_runs WHERE run_id = $1",
            run_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return {
        "run_id": row["run_id"],
        "status": row["status"],
        "trace": row["result"],
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
    }
```

### 8.4 Trace Diffing for Debugging

Compare two pipeline runs to understand performance differences:

```python
from stroma import ExecutionTrace

# Load two traces from the database
trace_monday = ExecutionTrace.from_json(monday_result["trace"])
trace_tuesday = ExecutionTrace.from_json(tuesday_result["trace"])

diffs = trace_monday.diff(trace_tuesday)
for diff in diffs:
    print(diff)
    # e.g., "Node 'scrape' duration changed from 45000ms to 132000ms"
    # e.g., "Node 'embed' gained failure on attempt 1: RECOVERABLE"
```

---

## 9. Docker + Infrastructure Changes

### 9.1 Add Redis Service

**`docker-compose.yml`** (add Redis):

```yaml
services:
  app:
    build: .
    ports:
      - "8001:8000"
    env_file: .env
    environment:
      DATABASE_URL: postgresql://mcgill:mcgilldev@postgres:5432/mcgill
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: mcgilldev
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      neo4j:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./data:/app/data

  postgres:
    image: pgvector/pgvector:pg17
    ports:
      - "5433:5432"
    environment:
      POSTGRES_USER: mcgill
      POSTGRES_PASSWORD: mcgilldev
      POSTGRES_DB: mcgill
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U mcgill"]
      interval: 5s
      timeout: 3s
      retries: 5

  neo4j:
    image: neo4j:5-community
    ports:
      - "7688:7687"
      - "7475:7474"
    environment:
      NEO4J_AUTH: neo4j/mcgilldev
      NEO4J_PLUGINS: '["apoc"]'
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
    healthcheck:
      test: ["CMD", "neo4j", "status"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  pgdata:
  neo4j_data:
  neo4j_logs:
  redis_data:
```

### 9.2 Add REDIS_URL to Settings

**`backend/config.py`** (add field):

```python
class Settings(BaseSettings):
    # ... existing fields ...

    # Redis (Stroma checkpointing)
    redis_url: str = "redis://localhost:6379/0"
```

---

## 10. Dependency Impact

| Dependency | Version | Purpose | Already Satisfied? |
|------------|---------|---------|-------------------|
| `stroma` | 0.3.0+ | Core reliability primitives | New |
| `pydantic` | 2.0+ | Contract schemas | Yes (`>=2.12.5`) |
| `langgraph` | 0.2+ | Adapter target | Yes (`>=1.1.3`) |
| `redis` | 5.0+ | Checkpoint backend | New (via `stroma[redis]`) |

**No breaking changes** to the existing API surface or frontend. The `LangGraphAdapter` wraps compiled graphs in-place. Existing `WorkflowOrchestrator.run()` and `.stream()` methods continue to work — Stroma validation runs inside the graph execution, invisible to callers.

### Phased Rollout Summary

| Phase | Scope | Risk | Value |
|-------|-------|------|-------|
| 1 | Install + contract definitions | None (no runtime changes) | Foundation |
| 2 | Wrap ingest pipeline | Low (longest, most failure-prone workflow) | High — retry, resume, validation |
| 3 | Wrap retrieval + synthesis | Low (hot path, but graceful degradation) | Medium — cost visibility, validation |
| 4 | Budget caps on planner | Low (adds safety, doesn't change behavior) | High — prevents runaway costs |
| 5 | Observability | None (additive) | Medium — trace diffing, audit trail |

### File Summary

```
New files:
  backend/contracts/__init__.py          — contract re-exports
  backend/contracts/ingest.py            — ingest node contracts
  backend/contracts/retrieval.py         — retrieval node contracts
  backend/contracts/synthesis.py         — synthesis node contracts
  backend/contracts/planner.py           — planner node contracts
  backend/lib/contracts.py               — ContractRegistry builder
  backend/lib/classifiers.py             — failure classifiers for external services
  backend/lib/hooks.py                   — structured logging hooks
  backend/workflows/ingest/runner.py     — StromaRunner-based ingest with checkpointing
  backend/workflows/planner/runner.py    — StromaRunner-based planner with budget

Modified files:
  backend/workflows/ingest/nodes.py      — add @stroma_langgraph_node decorators, remove try/except
  backend/workflows/ingest/graph.py      — add LangGraphAdapter.wrap()
  backend/workflows/retrieval/nodes.py   — add @stroma_langgraph_node decorators
  backend/workflows/retrieval/graph.py   — add LangGraphAdapter.wrap()
  backend/workflows/synthesis/nodes.py   — add @stroma_langgraph_node decorators
  backend/workflows/synthesis/graph.py   — add LangGraphAdapter.wrap()
  backend/config.py                      — add redis_url setting
  docker-compose.yml                     — add Redis service
  pyproject.toml                         — add stroma[langgraph,redis] dependency
```
