# McGill Architecture Redesign — Claude Code Instructions

## Goal

Refactor `src/mcgill/` into a layered backend architecture that:
1. Separates a reusable orchestration framework from domain workflow implementations
2. Supports multiple independent agentic workflows
3. Fixes the API-layer business logic problem
4. Keeps all existing functionality intact during migration

---

## Step 0 — Rename src/mcgill → backend

```bash
mv src/mcgill backend
```

Update `pyproject.toml`:
- Change `packages = [{include = "mcgill", from = "src"}]` to `packages = [{include = "backend"}]`
- Change the console script entry point from `mcgill.main:cli` to `backend.main:cli`

Update all internal imports throughout the codebase from `mcgill.*` to `backend.*`.

Update `Dockerfile`:
- Change `COPY src/ src/` to `COPY backend/ backend/`
- Change the uvicorn target from `mcgill.api.app:create_app` to `backend.api.app:create_app`

---

## Step 1 — Create the target directory structure

Create the following empty `__init__.py` files to establish the new package layout. Do not move any existing files yet.

```
backend/
├── lib/                          # Reusable orchestration framework (no domain knowledge)
│   ├── __init__.py
│   ├── orchestrator.py           # WorkflowOrchestrator ABC
│   ├── registry.py               # WorkflowRegistry + WorkflowConfig
│   ├── state.py                  # BaseWorkflowState TypedDict
│   ├── sse.py                    # SSE event helpers shared across workflows
│   └── streaming.py              # Async generator + StreamingResponse factory
│
├── workflows/                    # One sub-package per agentic workflow
│   ├── __init__.py
│   ├── ingest/                   # Scrape → Resolve → Chunk → Embed (current pipeline)
│   │   ├── __init__.py
│   │   ├── graph.py
│   │   ├── nodes.py
│   │   └── state.py
│   ├── retrieval/                # Hybrid dense + sparse retrieval workflow
│   │   ├── __init__.py
│   │   ├── graph.py
│   │   ├── nodes.py
│   │   └── state.py
│   ├── ingestion/                # PDF ingestion workflow
│   │   ├── __init__.py
│   │   ├── graph.py
│   │   ├── nodes.py
│   │   └── state.py
│   └── synthesis/                # Curriculum assembler / advisor synthesis workflow
│       ├── __init__.py
│       ├── graph.py
│       ├── nodes.py
│       └── state.py
│
├── services/                     # Stateless domain services (no LangGraph knowledge)
│   ├── __init__.py
│   ├── scraping/                 # Browser, parser, faculties registry
│   │   ├── __init__.py
│   │   ├── browser.py            # (moved from scraper/browser.py)
│   │   ├── catalogue.py          # (moved from scraper/catalogue.py)
│   │   ├── faculties.py          # (moved from scraper/faculties.py)
│   │   └── parser.py             # (moved from scraper/parser.py)
│   ├── resolution/               # Entity resolution services
│   │   ├── __init__.py
│   │   ├── entity_graph.py       # (moved from resolver/entity_graph.py)
│   │   ├── jaro_winkler.py       # (moved from resolver/jaro_winkler.py)
│   │   ├── normalize.py          # (moved from resolver/normalize.py)
│   │   └── prerequisites.py      # (moved from resolver/prerequisites.py)
│   ├── embedding/                # Chunking, embedding, vector store, retrieval
│   │   ├── __init__.py
│   │   ├── chunker.py            # (moved from embeddings/chunker.py)
│   │   ├── retrieval.py          # (moved from embeddings/retrieval.py)
│   │   ├── vector_store.py       # (moved from embeddings/vector_store.py)
│   │   └── voyage.py             # (moved from embeddings/voyage.py)
│   ├── pdf/                      # PDF extraction service
│   │   ├── __init__.py
│   │   └── extractor.py          # NEW — PDF → structured text
│   └── synthesis/                # Curriculum synthesis service
│       ├── __init__.py
│       └── curriculum.py         # NEW — interest mapping + program assembly
│
├── db/                           # (unchanged — postgres.py, neo4j.py, migrations.py)
├── models/                       # (unchanged — course.py, faculty.py, graph.py, chat.py)
├── api/                          # (unchanged structure — app.py, deps.py, routes/)
├── config.py                     # (unchanged)
└── main.py                       # (unchanged)
```

---

## Step 2 — Build backend/lib/state.py

Create `BaseWorkflowState` as a `TypedDict` that all workflow states extend. It must carry:
- `run_id: str`
- `errors: Annotated[list[str], add]` (uses `operator.add` for LangGraph merge)
- `status: str` — one of `"pending" | "running" | "complete" | "error"`

Do not add any domain fields here.

---

## Step 3 — Build backend/lib/orchestrator.py

Create `WorkflowOrchestrator` as an abstract base class with the following interface:

```python
class WorkflowOrchestrator(ABC):
    @abstractmethod
    def build_graph(self) -> CompiledGraph: ...

    @abstractmethod
    def build_initial_state(self, **kwargs) -> BaseWorkflowState: ...

    async def run(self, **kwargs) -> BaseWorkflowState:
        # compile graph, invoke with initial state, return final state

    async def stream(self, on_event: Callable[[dict], None], **kwargs) -> BaseWorkflowState:
        # compile graph, astream_events, call on_event for each, return final state
```

The `stream` method must:
1. Call `build_initial_state(**kwargs)` to get the initial state
2. Call `build_graph()` to get the compiled graph
3. Use `graph.astream_events(initial_state, version="v2")` to iterate
4. For each event with `event == "on_chain_end"` where `name` matches a node name, call `on_event` with a progress dict containing `phase`, `node`, `status: "done"`
5. Return the final accumulated state

Do NOT import anything from `backend.workflows` or `backend.services` in this file. It must have zero domain knowledge.

---

## Step 4 — Build backend/lib/registry.py

Create two dataclasses:

```python
@dataclass
class WorkflowConfig:
    name: str
    orchestrator_class: type[WorkflowOrchestrator]
    description: str = ""

@dataclass
class WorkflowRegistry:
    _registry: dict[str, WorkflowConfig] = field(default_factory=dict)

    def register(self, config: WorkflowConfig) -> None: ...
    def get(self, name: str) -> WorkflowConfig: ...
    def list_workflows(self) -> list[str]: ...
```

Create a module-level singleton: `registry = WorkflowRegistry()`

---

## Step 5 — Build backend/lib/sse.py

Extract the `_sse(data: dict) -> str` helper that currently exists as a local function in both `api/routes/pipeline.py` and `api/routes/chat.py` into this shared module.

Also add:
```python
def progress_event(phase: str, message: str, current: int = 0, total: int = 0) -> str: ...
def error_event(message: str) -> str: ...
def done_event(result: dict) -> str: ...
```

---

## Step 6 — Migrate the ingest workflow

### 6a — Move and update state

Move `pipeline/state.py` to `workflows/ingest/state.py`.

Change `IngestState` to extend `BaseWorkflowState`:
```python
class IngestState(BaseWorkflowState, total=False):
    faculty_filter: list[str] | None
    dept_filter: list[str] | None
    max_course_pages: int | None
    max_program_pages: int | None
    courses_scraped: int
    scrape_status: str
    entities_created: int
    relationships_created: int
    resolve_status: str
    chunks_created: int
    embed_status: str
```

Remove `run_id` and `errors` from `IngestState` since they are now inherited from `BaseWorkflowState`.

### 6b — Move and update nodes

Move `pipeline/nodes.py` to `workflows/ingest/nodes.py`.

Update all imports from `mcgill.*` to `backend.*`, and from `backend.embeddings.*` to `backend.services.embedding.*`, from `backend.resolver.*` to `backend.services.resolution.*`, from `backend.scraper.*` to `backend.services.scraping.*`.

Each node function signature stays the same: `async def scrape_node(state: IngestState) -> IngestState`.

### 6c — Create IngestOrchestrator

Create `workflows/ingest/graph.py`:

```python
class IngestOrchestrator(WorkflowOrchestrator):
    def build_graph(self) -> CompiledGraph:
        # Move the graph construction logic from pipeline/graph.py here
        # build_pipeline() + compile_pipeline() collapse into this method

    def build_initial_state(self, faculty_filter=None, dept_filter=None,
                             max_course_pages=None, max_program_pages=None) -> IngestState:
        return IngestState(
            run_id=str(uuid.uuid4()),
            errors=[],
            status="pending",
            faculty_filter=faculty_filter,
            ...
        )
```

Register it at module level:
```python
from backend.lib.registry import registry, WorkflowConfig
registry.register(WorkflowConfig(name="ingest", orchestrator_class=IngestOrchestrator))
```

Delete `pipeline/graph.py`, `pipeline/nodes.py`, `pipeline/state.py`, and `pipeline/__init__.py` after migration is confirmed.

---

## Step 7 — Migrate services

### Scraping services
Move files one-to-one — no logic changes:
- `scraper/browser.py` → `services/scraping/browser.py`
- `scraper/catalogue.py` → `services/scraping/catalogue.py`
- `scraper/faculties.py` → `services/scraping/faculties.py`
- `scraper/parser.py` → `services/scraping/parser.py`

Delete `scraper/` directory.

### Resolution services
Move files one-to-one:
- `resolver/entity_graph.py` → `services/resolution/entity_graph.py`
- `resolver/jaro_winkler.py` → `services/resolution/jaro_winkler.py`
- `resolver/normalize.py` → `services/resolution/normalize.py`
- `resolver/prerequisites.py` → `services/resolution/prerequisites.py`

Delete `resolver/` directory.

### Embedding services
Move files one-to-one:
- `embeddings/chunker.py` → `services/embedding/chunker.py`
- `embeddings/retrieval.py` → `services/embedding/retrieval.py`
- `embeddings/vector_store.py` → `services/embedding/vector_store.py`
- `embeddings/voyage.py` → `services/embedding/voyage.py`

Delete `embeddings/` directory.

After each move, do a global find-and-replace on imports in the affected files and anywhere they are imported from.

---

## Step 8 — Fix api/routes/pipeline.py

The current `pipeline.py` route directly orchestrates scrape → resolve → embed inline in `_execute_pipeline()`. This is wrong — the route should not know about chunking, embedding batch sizes, or any domain operations.

Replace `_execute_pipeline()` with:

```python
async def _execute_pipeline(run_id: str, req: PipelineRequest):
    from backend.workflows.ingest.graph import IngestOrchestrator
    from backend.lib.sse import progress_event, done_event, error_event

    run = _runs[run_id]
    run["status"] = "running"

    orchestrator = IngestOrchestrator()

    def on_event(event: dict):
        run["progress"].append(event)

    try:
        final_state = await orchestrator.stream(
            on_event=on_event,
            faculty_filter=req.faculty_filter,
            dept_filter=req.dept_filter,
            max_course_pages=req.max_course_pages,
            max_program_pages=req.max_program_pages,
        )
        run["status"] = final_state.get("status", "complete")
        run["result"] = {
            "courses_scraped": final_state.get("courses_scraped", 0),
            "entities_created": final_state.get("entities_created", 0),
            "relationships_created": final_state.get("relationships_created", 0),
            "chunks_created": final_state.get("chunks_created", 0),
        }
    except Exception as e:
        run["status"] = "error"
        run["result"] = {"error": str(e)}
```

---

## Step 9 — Fix api/routes/chat.py

The current `_run_chat_pipeline()` in `chat.py` does retrieval, graph queries, and synthesis inline with bare `except: pass` blocks. This needs to be replaced with a proper workflow.

### 9a — Create the retrieval workflow

Create `workflows/retrieval/state.py`:
```python
class RetrievalState(BaseWorkflowState, total=False):
    query: str
    top_k: int
    mode: str  # "keyword" | "semantic" | "hybrid"
    keyword_results: list[dict]
    semantic_results: list[dict]
    program_results: list[dict]
    graph_context: str
    fused_results: list[dict]
```

Create `workflows/retrieval/nodes.py` with these node functions (each takes and returns `RetrievalState`):
- `keyword_node` — calls `services/embedding/retrieval.py:keyword_search`
- `semantic_node` — calls `services/embedding/retrieval.py:semantic_search`
- `program_node` — calls `services/embedding/retrieval.py:program_search`
- `graph_node` — runs Neo4j prerequisite query if course codes detected in query
- `fusion_node` — calls `reciprocal_rank_fusion` on the results

Create `workflows/retrieval/graph.py` with `RetrievalOrchestrator(WorkflowOrchestrator)`.

The graph topology should be: parallel fan-out of `keyword_node`, `semantic_node`, `program_node`, `graph_node` → fan-in at `fusion_node`.

Use `send` or parallel node execution via LangGraph's `add_node` with a fan-out conditional. Specifically: after entry, branch to all four retrieval nodes; set a `check_ready` conditional that waits for all four to populate their result fields before routing to `fusion_node`.

### 9b — Create the synthesis workflow

Create `workflows/synthesis/state.py`:
```python
class SynthesisState(BaseWorkflowState, total=False):
    query: str
    session_id: str
    conversation_history: list[dict]
    retrieval_context: list[dict]
    program_context: str
    graph_context: str
    response: str
    sources: list[dict]
```

Create `workflows/synthesis/nodes.py` with:
- `context_pack_node` — assembles retrieval context into a Claude-ready string, trims to token budget
- `synthesize_node` — calls Anthropic API with system prompt + packed context + conversation history, streams response tokens

Create `workflows/synthesis/graph.py` with `SynthesisOrchestrator(WorkflowOrchestrator)`.

### 9c — Update chat.py route

Replace `_run_chat_pipeline()` with:

```python
async def _run_chat_pipeline(question: str, session_id: str) -> AsyncIterator[dict]:
    from backend.workflows.retrieval.graph import RetrievalOrchestrator
    from backend.workflows.synthesis.graph import SynthesisOrchestrator

    session = _sessions.get(session_id, {})

    # Step 1: Run retrieval workflow
    yield {"type": "step_update", "phase": 1, "status": "running", "label": "Retrieval"}
    retrieval_orch = RetrievalOrchestrator()
    retrieval_state = await retrieval_orch.run(query=question, top_k=10, mode="hybrid")
    yield {"type": "step_update", "phase": 1, "status": "done", "label": "Retrieval"}

    sources = [
        {"code": r.get("code", ""), "title": r.get("title", "")}
        for r in retrieval_state.get("fused_results", [])[:5]
    ]
    if sources:
        yield {"type": "sources", "sources": sources}

    # Step 2: Run synthesis workflow
    yield {"type": "step_update", "phase": 2, "status": "running", "label": "Synthesis"}
    synthesis_orch = SynthesisOrchestrator()
    synthesis_state = await synthesis_orch.run(
        query=question,
        session_id=session_id,
        conversation_history=session.get("messages", [])[-6:],
        retrieval_context=retrieval_state.get("fused_results", []),
        program_context=retrieval_state.get("program_results", []),
        graph_context=retrieval_state.get("graph_context", ""),
    )
    yield {"type": "step_update", "phase": 2, "status": "done", "label": "Synthesis"}

    answer = synthesis_state.get("response", "")
    if answer:
        yield {"type": "assistant", "content": answer}
        _sessions[session_id]["messages"].append({"role": "assistant", "content": answer})
```

---

## Step 10 — Create the PDF ingestion workflow

Create `services/pdf/extractor.py`:

```python
class PDFExtractor:
    def extract_text(self, pdf_bytes: bytes) -> str:
        # Use pymupdf (fitz) as primary extractor
        # Fall back to pdfplumber if fitz returns < 100 chars
        # Return raw text string

    def extract_structured(self, pdf_bytes: bytes) -> dict:
        # Returns {"title": str, "sections": list[{"heading": str, "text": str}]}
        # Use heuristics: lines in ALL CAPS or bold-weight at start of page = heading
```

Add `pymupdf` and `pdfplumber` to `pyproject.toml` dependencies.

Create `workflows/ingestion/state.py`:
```python
class IngestionState(BaseWorkflowState, total=False):
    source_type: str  # "pdf" | "url" | "html"
    source_path: str
    faculty_slug: str
    raw_text: str
    structured_sections: list[dict]
    chunks: list[str]
    embeddings: list[list[float]]
    chunks_stored: int
```

Create `workflows/ingestion/nodes.py` with:
- `extract_node` — calls `PDFExtractor.extract_structured()` or fetches URL via existing `browser.py`
- `chunk_node` — calls `services/embedding/chunker.py:chunk_program_page` on extracted sections
- `embed_node` — calls `services/embedding/voyage.py:embed_texts`
- `store_node` — calls `services/embedding/vector_store.py:insert_program_chunks`

Add a new API route `POST /api/v1/ingest/pdf` that accepts a file upload and faculty slug, triggers `IngestionOrchestrator`, streams progress via SSE.

---

## Step 11 — Create the synthesis / curriculum assembly workflow

This is the most novel workflow. It synthesizes a student's interests and program of study into structured course recommendations.

Create `services/synthesis/curriculum.py`:

```python
class CurriculumAssembler:
    def map_interests_to_domains(self, interests: list[str]) -> list[str]:
        # Maps free-text interests to canonical domain tags
        # e.g. "machine learning" → ["COMP", "MATH", "STAT"]

    def resolve_program_requirements(self, program_slug: str) -> dict:
        # Queries program_pages for required/elective course lists
        # Returns {"required": list[str], "electives": list[str], "credits_needed": int}

    def detect_conflicts(self, course_codes: list[str]) -> list[dict]:
        # Queries Neo4j for schedule conflicts and restriction violations
```

Create `workflows/synthesis/state.py`:
```python
class CurriculumState(BaseWorkflowState, total=False):
    student_interests: list[str]
    program_slug: str
    completed_codes: list[str]
    domain_tags: list[str]
    program_requirements: dict
    candidate_courses: list[dict]
    ranked_courses: list[dict]
    conflicts: list[dict]
    recommendation: str
```

Create `workflows/synthesis/nodes.py` with:
- `interest_map_node` — calls `CurriculumAssembler.map_interests_to_domains`
- `requirements_node` — calls `CurriculumAssembler.resolve_program_requirements`
- `candidate_retrieval_node` — calls `RetrievalOrchestrator.run()` with domain tags as query (workflows calling workflows is fine)
- `prereq_filter_node` — filters candidate_courses by checking Neo4j that all prerequisites are in completed_codes
- `conflict_node` — calls `CurriculumAssembler.detect_conflicts`
- `rank_node` — scores candidates by interest alignment + requirement coverage + prereq readiness
- `assemble_node` — calls Anthropic API to write a natural language curriculum plan from ranked courses

Add a new API route `POST /api/v1/curriculum/recommend` that accepts `{student_interests, program_slug, completed_codes}` and streams the curriculum assembly via SSE.

---

## Step 12 — Register all workflows

Create `backend/workflows/__init__.py` that imports and registers all orchestrators:

```python
from backend.workflows.ingest.graph import IngestOrchestrator
from backend.workflows.retrieval.graph import RetrievalOrchestrator
from backend.workflows.ingestion.graph import IngestionOrchestrator
from backend.workflows.synthesis.graph import SynthesisOrchestrator
from backend.lib.registry import registry, WorkflowConfig

registry.register(WorkflowConfig(name="ingest", orchestrator_class=IngestOrchestrator, description="Scrape → resolve → chunk → embed"))
registry.register(WorkflowConfig(name="retrieval", orchestrator_class=RetrievalOrchestrator, description="Hybrid dense + sparse retrieval with RRF fusion"))
registry.register(WorkflowConfig(name="ingestion", orchestrator_class=IngestionOrchestrator, description="PDF / URL ingestion → chunk → embed"))
registry.register(WorkflowConfig(name="synthesis", orchestrator_class=SynthesisOrchestrator, description="Curriculum assembly and advisor synthesis"))
```

Import `backend.workflows` in `backend/api/app.py` lifespan so all workflows are registered at startup.

---

## Step 13 — Update API app.py

In `backend/api/app.py`, add the two new routers:

```python
from backend.api.routes.ingestion import router as ingestion_router
from backend.api.routes.curriculum import router as curriculum_router

app.include_router(ingestion_router, prefix="/api/v1")
app.include_router(curriculum_router, prefix="/api/v1")
```

Create stub files for `api/routes/ingestion.py` and `api/routes/curriculum.py` with `TODO` comments — do not implement them until the workflow layer is confirmed working.

---

## Step 14 — Update main.py CLI

Add two new CLI subcommands:

```
ingest-pdf    Ingest a PDF file into a faculty's program page store
curriculum    Generate a curriculum recommendation for a student
```

Both should call `asyncio.run(orchestrator.run(...))` directly, not go through the API layer.

---

## Step 15 — Run tests and validate

```bash
make test
make typecheck
make lint
```

Fix any import errors. The test suite should pass without changes to test files since the public API surface (routes, CLI commands, make targets) is unchanged.

After tests pass, run:
```bash
make seed
make serve
```

Confirm `GET /api/v1/faculties` and `GET /health` still return correctly.

---

## Constraints and guardrails for Claude Code

- Do NOT change any `db/` files during this refactor
- Do NOT change any `models/` files during this refactor  
- Do NOT change `Makefile` targets — only update the commands they execute if needed
- Each step should be committed separately so the migration is reversible
- If a file is being moved (not rewritten), move it first and fix imports, do not rewrite logic simultaneously
- The `lib/` layer must have zero imports from `workflows/` or `services/` — enforce this with a comment at the top of each file in `lib/`
- Node functions must not import from `api/` — they are below the API layer
- Services must not import from `workflows/` or `lib/` — they are the lowest layer

---

## Final directory tree (target state)

```
backend/
├── lib/
│   ├── orchestrator.py     # WorkflowOrchestrator ABC — zero domain knowledge
│   ├── registry.py         # WorkflowRegistry singleton
│   ├── state.py            # BaseWorkflowState
│   ├── sse.py              # Shared SSE helpers
│   └── streaming.py        # StreamingResponse factory
│
├── workflows/
│   ├── __init__.py         # Registers all workflows into registry
│   ├── ingest/             # Scrape → resolve → chunk → embed
│   ├── retrieval/          # Keyword + semantic + graph → RRF fusion
│   ├── ingestion/          # PDF / URL → chunk → embed
│   └── synthesis/          # Curriculum assembly → ranked recommendations
│
├── services/
│   ├── scraping/           # Browser, parser, catalogue, faculties
│   ├── resolution/         # Jaro-Winkler, entity graph, prerequisites, normalize
│   ├── embedding/          # Chunker, voyage, vector_store, retrieval
│   ├── pdf/                # PDF extractor
│   └── synthesis/          # Curriculum assembler
│
├── db/                     # postgres.py, neo4j.py, migrations.py (unchanged)
├── models/                 # course.py, faculty.py, graph.py, chat.py (unchanged)
├── api/
│   ├── app.py              # Lifespan imports backend.workflows to trigger registration
│   ├── deps.py
│   └── routes/
│       ├── health.py
│       ├── faculties.py
│       ├── courses.py
│       ├── search.py
│       ├── pipeline.py     # Delegates to IngestOrchestrator only
│       ├── chat.py         # Delegates to RetrievalOrchestrator + SynthesisOrchestrator
│       ├── ingestion.py    # NEW — PDF upload endpoint
│       └── curriculum.py  # NEW — curriculum recommendation endpoint
│
├── config.py
└── main.py
```
