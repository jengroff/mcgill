from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import AsyncIterator

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.api.auth import get_current_user, get_optional_user
from backend.api.deps import get_db
from backend.lib.sse import _sse
from backend.lib.streaming import sse_response

logger = logging.getLogger("backend.api.chat")

router = APIRouter()

_sessions: dict[str, dict] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class SessionRequest(BaseModel):
    session_id: str | None = None


# ---------------------------------------------------------------------------
# Helpers — message persistence
# ---------------------------------------------------------------------------

def _generate_title(text: str) -> str:
    """Create a conversation title from the first user message (max 60 chars, word boundary)."""
    text = text.strip().replace("\n", " ")
    if len(text) <= 60:
        return text
    truncated = text[:60]
    last_space = truncated.rfind(" ")
    if last_space > 20:
        truncated = truncated[:last_space]
    return truncated + "..."


async def _persist_message(
    pool: asyncpg.Pool,
    conversation_id: int,
    role: str,
    content: str,
    metadata: dict | None = None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO messages (conversation_id, role, content, metadata)
               VALUES ($1, $2, $3, $4)""",
            conversation_id,
            role,
            content,
            json.dumps(metadata or {}),
        )
        await conn.execute(
            "UPDATE conversations SET updated_at = now() WHERE id = $1",
            conversation_id,
        )


async def _load_messages_from_db(pool: asyncpg.Pool, conversation_id: int) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT role, content FROM messages
               WHERE conversation_id = $1 ORDER BY created_at""",
            conversation_id,
        )
    return [{"role": r["role"], "content": r["content"]} for r in rows]


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def _init_session(session_id: str) -> dict:
    if session_id not in _sessions:
        _sessions[session_id] = {
            "messages": [],
            "status": "idle",
            "event_queue": asyncio.Queue(),
            "bg_tasks": {},
        }
    session = _sessions[session_id]
    if "event_queue" not in session:
        session["event_queue"] = asyncio.Queue()
    if "bg_tasks" not in session:
        session["bg_tasks"] = {}
    return session


@router.post("/session")
async def create_session(
    body: SessionRequest = SessionRequest(),
    user: dict | None = Depends(get_optional_user),
    pool: asyncpg.Pool = Depends(get_db),
):
    """Create a new chat session or resume an existing one.

    If `session_id` is provided in the body, the endpoint loads the existing
    conversation from the database (when authenticated) and populates the
    in-memory session cache. Otherwise a fresh session is created.

    Auth is optional — anonymous users get a session without DB persistence.
    """
    # Resume existing session
    if body.session_id:
        session_id = body.session_id
        session = _init_session(session_id)

        if user:
            async with pool.acquire() as conn:
                conv = await conn.fetchrow(
                    """SELECT id FROM conversations
                       WHERE session_id = $1 AND user_id = $2""",
                    uuid.UUID(session_id),
                    user["id"],
                )
            if conv:
                session["conversation_id"] = conv["id"]
                if not session["messages"]:
                    session["messages"] = await _load_messages_from_db(pool, conv["id"])

        return {"session_id": session_id}

    # New session
    session_id = str(uuid.uuid4())
    session = _init_session(session_id)

    if user:
        async with pool.acquire() as conn:
            conv = await conn.fetchrow(
                """INSERT INTO conversations (user_id, session_id)
                   VALUES ($1, $2) RETURNING id""",
                user["id"],
                uuid.UUID(session_id),
            )
        session["conversation_id"] = conv["id"]

    return {"session_id": session_id}


@router.post("/ask")
async def ask(
    req: ChatRequest,
    user: dict | None = Depends(get_optional_user),
    pool: asyncpg.Pool = Depends(get_db),
):
    session_id = req.session_id or str(uuid.uuid4())
    session = _init_session(session_id)

    session["messages"].append({"role": "user", "content": req.message})
    session["status"] = "processing"
    session["pending_question"] = req.message

    conv_id = session.get("conversation_id")

    # If authenticated but session has no conversation yet, create one
    if user and not conv_id:
        async with pool.acquire() as conn:
            conv = await conn.fetchrow(
                """INSERT INTO conversations (user_id, session_id, title)
                   VALUES ($1, $2, $3) RETURNING id""",
                user["id"],
                uuid.UUID(session_id),
                _generate_title(req.message),
            )
        conv_id = conv["id"]
        session["conversation_id"] = conv_id

    if conv_id:
        # Set title from first user message if still empty
        async with pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT title FROM conversations WHERE id = $1", conv_id,
            )
        if not existing:
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE conversations SET title = $1 WHERE id = $2",
                    _generate_title(req.message),
                    conv_id,
                )

        await _persist_message(pool, conv_id, "user", req.message)

    return {"session_id": session_id, "status": "processing"}


@router.get("/stream")
async def stream(session_id: str, request: Request):
    session = _init_session(session_id)

    async def event_generator() -> AsyncIterator[str]:
        yield _sse({"type": "session_started", "session_id": session_id})

        while not await request.is_disconnected():
            queue: asyncio.Queue = session["event_queue"]
            while not queue.empty():
                try:
                    event = queue.get_nowait()
                    yield _sse(event)
                except asyncio.QueueEmpty:
                    break

            if session.get("status") == "processing" and session.get("pending_question"):
                question = session.pop("pending_question")
                session["status"] = "streaming"

                pipeline_intent = _detect_pipeline_intent(question)
                planner_intent = _detect_planner_intent(question)
                if pipeline_intent:
                    _spawn_pipeline(session_id, pipeline_intent)
                    session["status"] = "idle"
                elif planner_intent:
                    _spawn_planner(session_id, planner_intent)
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
# Conversation history endpoints (protected)
# ---------------------------------------------------------------------------

@router.get("/conversations")
async def list_conversations(
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
):
    """Return all conversations for the authenticated user, most recent first."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, session_id, title, updated_at
               FROM conversations
               WHERE user_id = $1
               ORDER BY updated_at DESC""",
            user["id"],
        )
    return [
        {
            "id": r["id"],
            "session_id": str(r["session_id"]),
            "title": r["title"],
            "updated_at": r["updated_at"].isoformat(),
        }
        for r in rows
    ]


@router.get("/conversations/{session_id}/messages")
async def get_conversation_messages(
    session_id: str,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
):
    """Return the full message history for a conversation owned by the authenticated user."""
    async with pool.acquire() as conn:
        conv = await conn.fetchrow(
            """SELECT id FROM conversations
               WHERE session_id = $1 AND user_id = $2""",
            uuid.UUID(session_id),
            user["id"],
        )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT role, content, metadata, created_at
               FROM messages
               WHERE conversation_id = $1
               ORDER BY created_at""",
            conv["id"],
        )
    return [
        {
            "role": r["role"],
            "content": r["content"],
            "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

def _detect_pipeline_intent(message: str) -> dict | None:
    """Detect if the user wants to trigger a pipeline run.

    Uses keyword gate + noise-word stripping to extract faculty/department target.
    Returns `{"faculty_filter": [...], "dept_filter": [...]}` or None.
    """
    from backend.services.scraping.faculties import ALL_FACULTIES

    lower = message.lower()

    trigger_words = ("scrape", "pipeline", "ingest", "crawl", "fetch", "refresh", "load", "download")
    if not any(w in lower for w in trigger_words):
        return None

    all_dept_codes = {p for _, _, prefixes in ALL_FACULTIES for p in prefixes}
    slug_map = {slug: slug for _, slug, _ in ALL_FACULTIES}
    name_map = {name.lower(): slug for name, slug, _ in ALL_FACULTIES}

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

    upper = candidate.upper()
    if upper in all_dept_codes:
        return {"dept_filter": [upper], "faculty_filter": None}

    if candidate in slug_map:
        return {"faculty_filter": [candidate], "dept_filter": None}
    if candidate in name_map:
        return {"faculty_filter": [name_map[candidate]], "dept_filter": None}

    for slug in slug_map:
        if slug in candidate or candidate in slug:
            return {"faculty_filter": [slug], "dept_filter": None}
    for name_lower, slug in name_map.items():
        if candidate in name_lower or name_lower.startswith(candidate):
            return {"faculty_filter": [slug], "dept_filter": None}

    for w in candidate_words:
        if w.upper() in all_dept_codes:
            return {"dept_filter": [w.upper()], "faculty_filter": None}

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
    run_id = str(uuid.uuid4())[:8]
    session = _sessions[session_id]
    queue: asyncio.Queue = session["event_queue"]

    faculty = intent.get("faculty_filter")
    dept = intent.get("dept_filter")
    target_label = f"dept {dept[0]}" if dept else f"faculty {faculty[0]}" if faculty else "all"

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

        await _persist_bg_message(session, summary)

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
    from backend.workflows.retrieval.graph import RetrievalOrchestrator
    from backend.workflows.synthesis.graph import SynthesisOrchestrator

    session = _sessions.get(session_id, {})

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

    yield {"type": "step_update", "phase": 2, "status": "running", "label": "Synthesis"}
    synthesis_orch = SynthesisOrchestrator()
    synthesis_state = await synthesis_orch.run(
        query=question,
        session_id=session_id,
        conversation_history=session.get("messages", [])[-6:],
        retrieval_context=retrieval_state.get("fused_results", []),
        program_context=retrieval_state.get("program_results", []),
        graph_context=retrieval_state.get("graph_context", ""),
        structured_context=retrieval_state.get("structured_context", ""),
    )
    yield {"type": "step_update", "phase": 2, "status": "done", "label": "Synthesis"}

    answer = synthesis_state.get("response", "")
    if answer:
        yield {"type": "assistant", "content": answer}
        _sessions[session_id]["messages"].append({"role": "assistant", "content": answer})

        await _persist_bg_message(_sessions[session_id], answer)


# ---------------------------------------------------------------------------
# Background message persistence helper
# ---------------------------------------------------------------------------

async def _persist_bg_message(session: dict, content: str) -> None:
    """Persist an assistant message to the DB if the session is linked to a conversation."""
    conv_id = session.get("conversation_id")
    if not conv_id:
        return
    try:
        from backend.db.postgres import get_pool
        pool = await get_pool()
        await _persist_message(pool, conv_id, "assistant", content)
    except Exception:
        logger.exception("Failed to persist background message")


# ---------------------------------------------------------------------------
# Curriculum planner intent detection + background execution
# ---------------------------------------------------------------------------

def _detect_planner_intent(message: str) -> dict | None:
    """Detect if the user wants to build a multi-semester curriculum plan.

    Returns `{"interests": [...], "semesters": int}` or None.
    """
    lower = message.lower()

    plan_triggers = ("plan my", "build a curriculum", "plan a curriculum", "semester plan",
                     "course plan", "plan my courses", "plan my schedule", "year plan",
                     "next year", "next two years", "next 2 years", "schedule for",
                     "curriculum for", "plan for next")
    if not any(t in lower for t in plan_triggers):
        return None

    semesters = 4
    sem_match = re.search(r"(\d+)\s*semester", lower)
    year_match = re.search(r"(\d+)\s*year", lower)
    if sem_match:
        semesters = int(sem_match.group(1))
    elif year_match:
        semesters = int(year_match.group(1)) * 2
    elif "next year" in lower:
        semesters = 2

    interests: list[str] = []
    interest_patterns = [
        r"interested?\s+in\s+(.+?)(?:\.|,\s*(?:and\s+)?plan|$)",
        r"(?:focus|focusing)\s+on\s+(.+?)(?:\.|,\s*(?:and\s+)?plan|$)",
        r"studying\s+(.+?)(?:\.|,\s*(?:and\s+)?plan|$)",
        r"major(?:ing)?\s+in\s+(.+?)(?:\.|,\s*(?:and\s+)?plan|$)",
    ]
    for pattern in interest_patterns:
        match = re.search(pattern, lower)
        if match:
            raw = match.group(1).strip()
            parts = re.split(r"\s*(?:,|and)\s*", raw)
            interests.extend(p.strip() for p in parts if p.strip())
            break

    if not interests:
        noise = {"plan", "my", "curriculum", "courses", "schedule", "build", "a", "for",
                 "next", "year", "years", "semester", "semesters", "the", "me", "please",
                 "can", "you", "i", "want", "to", "would", "like", "create", "make", "two", "2"}
        words = re.findall(r"[a-z]+", lower)
        interests = [w for w in words if w not in noise and len(w) > 2]

    return {"interests": interests, "semesters": semesters} if interests else None


def _spawn_planner(session_id: str, intent: dict) -> str:
    run_id = str(uuid.uuid4())[:8]
    session = _sessions[session_id]
    queue: asyncio.Queue = session["event_queue"]

    interests = intent.get("interests", [])
    semesters = intent.get("semesters", 4)
    label = f"{semesters}-semester plan for {', '.join(interests[:3])}"

    queue.put_nowait({
        "type": "assistant",
        "content": f"Building a **{semesters}-semester curriculum plan** based on your interests "
                   f"in **{', '.join(interests)}**. This may take a minute — the planning agent "
                   f"is analyzing courses, prerequisites, and term availability.",
    })
    queue.put_nowait({
        "type": "step_update",
        "phase": "planner",
        "label": label,
        "status": "running",
    })

    task = asyncio.create_task(
        _run_planner_bg(session_id, run_id, interests, semesters)
    )
    session["bg_tasks"][run_id] = task
    return run_id


async def _run_planner_bg(
    session_id: str,
    run_id: str,
    interests: list[str],
    semesters: int,
):
    from backend.workflows.planner.graph import PlannerOrchestrator

    session = _sessions[session_id]
    queue: asyncio.Queue = session["event_queue"]

    try:
        orchestrator = PlannerOrchestrator()
        result = await orchestrator.run(
            student_interests=interests,
            target_semesters=semesters,
        )

        plan_md = result.get("plan_markdown", "")
        errors = result.get("errors", [])

        if plan_md:
            queue.put_nowait({"type": "assistant", "content": plan_md})
            session["messages"].append({"role": "assistant", "content": plan_md})
            await _persist_bg_message(session, plan_md)
        elif errors:
            queue.put_nowait({
                "type": "error",
                "content": f"Planner encountered errors: {'; '.join(errors)}",
            })

        queue.put_nowait({
            "type": "step_update",
            "phase": "planner",
            "label": "Curriculum plan",
            "status": "done",
        })

    except Exception as e:
        logger.exception(f"Planner {run_id} failed")
        queue.put_nowait({"type": "error", "content": f"Planner failed: {e}"})
        queue.put_nowait({
            "type": "step_update",
            "phase": "planner",
            "label": "Curriculum plan",
            "status": "error",
        })
    finally:
        session["bg_tasks"].pop(run_id, None)
