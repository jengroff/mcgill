"""SSE streaming chat endpoint — delegates to retrieval + synthesis workflows."""

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


@router.post("/session")
async def create_session():
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {"messages": [], "status": "idle"}
    return {"session_id": session_id}


@router.post("/ask")
async def ask(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    if session_id not in _sessions:
        _sessions[session_id] = {"messages": [], "status": "idle"}

    _sessions[session_id]["messages"].append({"role": "user", "content": req.message})
    _sessions[session_id]["status"] = "processing"
    _sessions[session_id]["pending_question"] = req.message

    return {"session_id": session_id, "status": "processing"}


@router.get("/stream")
async def stream(session_id: str, request: Request):
    if session_id not in _sessions:
        _sessions[session_id] = {"messages": [], "status": "idle"}

    async def event_generator() -> AsyncIterator[str]:
        yield _sse({"type": "session_started", "session_id": session_id})

        while not await request.is_disconnected():
            session = _sessions.get(session_id, {})

            if session.get("status") == "processing" and session.get("pending_question"):
                question = session.pop("pending_question")
                session["status"] = "streaming"

                yield _sse({"type": "thinking", "content": "Searching courses..."})

                try:
                    async for chunk in _run_chat_pipeline(question, session_id):
                        if await request.is_disconnected():
                            break
                        yield _sse(chunk)
                except Exception as e:
                    logger.exception("Chat pipeline error")
                    yield _sse({"type": "error", "content": str(e)})

                session["status"] = "idle"

            await asyncio.sleep(0.2)

    return sse_response(event_generator())


async def _run_chat_pipeline(question: str, session_id: str) -> AsyncIterator[dict]:
    """Agentic chat pipeline: retrieve -> synthesize -> stream."""
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
