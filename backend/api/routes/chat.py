"""SSE streaming chat endpoint — delegates to retrieval + synthesis workflows.

Pipelines run as background tasks so the chat session remains responsive for Q&A.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.lib.sse import _sse
from backend.lib.streaming import sse_response

logger = logging.getLogger("backend.api.chat")

router = APIRouter()

_sessions: dict[str, dict] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


def _init_session(session_id: str) -> dict:
    if session_id not in _sessions:
        _sessions[session_id] = {
            "messages": [],
            "status": "idle",
            "event_queue": asyncio.Queue(),
            "bg_tasks": {},  # run_id -> asyncio.Task
        }
    # Ensure queue exists for older sessions
    session = _sessions[session_id]
    if "event_queue" not in session:
        session["event_queue"] = asyncio.Queue()
    if "bg_tasks" not in session:
        session["bg_tasks"] = {}
    return session


@router.post("/session")
async def create_session():
    session_id = str(uuid.uuid4())
    _init_session(session_id)
    return {"session_id": session_id}


@router.post("/ask")
async def ask(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    session = _init_session(session_id)

    session["messages"].append({"role": "user", "content": req.message})
    session["status"] = "processing"
    session["pending_question"] = req.message

    return {"session_id": session_id, "status": "processing"}


@router.get("/stream")
async def stream(session_id: str, request: Request):
    session = _init_session(session_id)

    async def event_generator() -> AsyncIterator[str]:
        yield _sse({"type": "session_started", "session_id": session_id})

        while not await request.is_disconnected():
            # Drain background pipeline events
            queue: asyncio.Queue = session["event_queue"]
            while not queue.empty():
                try:
                    event = queue.get_nowait()
                    yield _sse(event)
                except asyncio.QueueEmpty:
                    break

            # Handle new user questions
            if session.get("status") == "processing" and session.get("pending_question"):
                question = session.pop("pending_question")
                session["status"] = "streaming"

                # Check pipeline intent — if matched, spawn background task
                pipeline_intent = _detect_pipeline_intent(question)
                if pipeline_intent:
                    _spawn_pipeline(session_id, pipeline_intent)
                    session["status"] = "idle"
                else:
                    yield _sse({"type": "thinking", "content": "Searching courses..."})
                    try:
                        async for chunk in _run_qa_pipeline(question, session_id):
                            if await request.is_disconnected():
                                break
                            yield _sse(chunk)
                    except Exception as e:
                        logger.exception("Chat pipeline error")
                        yield _sse({"type": "error", "content": str(e)})
                    session["status"] = "idle"

            await asyncio.sleep(0.2)

    return sse_response(event_generator())


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

def _detect_pipeline_intent(message: str) -> dict | None:
    """Detect if the user wants to trigger a pipeline run.

    Uses keyword gate + noise-word stripping to extract faculty/department target.
    Returns {"faculty_filter": [...], "dept_filter": [...]} or None.
    """
    import re
    from backend.services.scraping.faculties import ALL_FACULTIES

    lower = message.lower()

    # Fast gate: must contain a trigger word
    trigger_words = ("scrape", "pipeline", "ingest", "crawl", "fetch", "refresh", "load", "download")
    if not any(w in lower for w in trigger_words):
        return None

    # Build lookup sets
    all_dept_codes = {p for _, _, prefixes in ALL_FACULTIES for p in prefixes}
    slug_map = {slug: slug for _, slug, _ in ALL_FACULTIES}
    name_map = {name.lower(): slug for name, slug, _ in ALL_FACULTIES}

    # Strip noise words to isolate the target
    noise = {"the", "a", "an", "for", "on", "of", "run", "please", "can", "you",
             "hi", "hey", "hello", "could", "would", "do", "start", "begin", "launch",
             "all", "some", "want", "to", "i", "me", "my", "it", "up", "is",
             "scrape", "pipeline", "ingest", "crawl", "fetch", "refresh", "load", "download",
             "faculty", "department", "dept", "courses", "course", "data", "program"}
    words = re.findall(r"[a-z0-9&()/\-]+", lower)
    candidate_words = [w for w in words if w not in noise]
    candidate = " ".join(candidate_words).strip().rstrip(".!?")

    if not candidate:
        return None

    # 1. Exact department code match
    upper = candidate.upper()
    if upper in all_dept_codes:
        return {"dept_filter": [upper], "faculty_filter": None}

    # 2. Exact faculty slug or name match
    if candidate in slug_map:
        return {"faculty_filter": [candidate], "dept_filter": None}
    if candidate in name_map:
        return {"faculty_filter": [name_map[candidate]], "dept_filter": None}

    # 3. Substring match against faculty slugs and names
    for slug in slug_map:
        if slug in candidate or candidate in slug:
            return {"faculty_filter": [slug], "dept_filter": None}
    for name_lower, slug in name_map.items():
        if candidate in name_lower or name_lower.startswith(candidate):
            return {"faculty_filter": [slug], "dept_filter": None}

    # 4. Per-word fallback for department codes
    for w in candidate_words:
        if w.upper() in all_dept_codes:
            return {"dept_filter": [w.upper()], "faculty_filter": None}

    # 5. Per-word fallback for faculty slugs
    for w in candidate_words:
        if w in slug_map:
            return {"faculty_filter": [w], "dept_filter": None}
        for name_lower, slug in name_map.items():
            if w in name_lower.split() or w == slug:
                return {"faculty_filter": [slug], "dept_filter": None}

    return None


# ---------------------------------------------------------------------------
# Background pipeline execution
# ---------------------------------------------------------------------------

def _spawn_pipeline(session_id: str, intent: dict) -> str:
    """Spawn a pipeline as a background task. Returns run_id."""
    run_id = str(uuid.uuid4())[:8]
    session = _sessions[session_id]
    queue: asyncio.Queue = session["event_queue"]

    faculty = intent.get("faculty_filter")
    dept = intent.get("dept_filter")
    target_label = f"dept {dept[0]}" if dept else f"faculty {faculty[0]}" if faculty else "all"

    # Immediately push a start message into the queue
    queue.put_nowait({
        "type": "assistant",
        "content": f"Starting ingest pipeline for **{target_label}** (run `{run_id}`). "
                   f"This runs in the background — you can keep asking questions.",
    })
    queue.put_nowait({
        "type": "pipeline_status",
        "run_id": run_id,
        "phase": "scrape",
        "status": "running",
        "label": target_label,
    })

    task = asyncio.create_task(
        _run_pipeline_bg(session_id, run_id, target_label, faculty, dept)
    )
    session["bg_tasks"][run_id] = task
    return run_id


async def _run_pipeline_bg(
    session_id: str,
    run_id: str,
    target_label: str,
    faculty: list[str] | None,
    dept: list[str] | None,
):
    """Background coroutine that runs the ingest pipeline and pushes events to the session queue."""
    from backend.workflows.ingest.graph import IngestOrchestrator

    session = _sessions[session_id]
    queue: asyncio.Queue = session["event_queue"]

    try:
        orchestrator = IngestOrchestrator()

        def on_event(event: dict):
            event["run_id"] = run_id
            queue.put_nowait(event)

        result = await orchestrator.stream(
            on_event=on_event,
            faculty_filter=faculty,
            dept_filter=dept,
        )

        courses = result.get("courses_scraped", 0)
        entities = result.get("entities_created", 0)
        rels = result.get("relationships_created", 0)
        chunks = result.get("chunks_created", 0)
        errors = result.get("errors", [])

        summary = f"Pipeline **{run_id}** complete for **{target_label}**:\n\n"
        summary += f"- **{courses}** courses scraped\n"
        summary += f"- **{entities}** entities created in Neo4j\n"
        summary += f"- **{rels}** relationships built\n"
        summary += f"- **{chunks}** chunks embedded\n"
        if errors:
            summary += f"\n**{len(errors)} errors** occurred during the run."

        queue.put_nowait({"type": "assistant", "content": summary})
        queue.put_nowait({
            "type": "pipeline_status",
            "run_id": run_id,
            "status": "complete",
            "label": target_label,
        })
        session["messages"].append({"role": "assistant", "content": summary})

    except Exception as e:
        logger.exception(f"Background pipeline {run_id} failed")
        queue.put_nowait({
            "type": "error",
            "content": f"Pipeline **{run_id}** failed: {e}",
        })
        queue.put_nowait({
            "type": "pipeline_status",
            "run_id": run_id,
            "status": "error",
            "label": target_label,
        })
    finally:
        session["bg_tasks"].pop(run_id, None)


# ---------------------------------------------------------------------------
# Q&A pipeline (retrieval + synthesis)
# ---------------------------------------------------------------------------

async def _run_qa_pipeline(question: str, session_id: str) -> AsyncIterator[dict]:
    """Retrieval + synthesis for normal Q&A."""
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
