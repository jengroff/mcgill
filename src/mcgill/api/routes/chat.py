"""SSE streaming chat endpoint — adapted from reat pattern."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("mcgill.api.chat")

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

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _run_chat_pipeline(question: str, session_id: str) -> AsyncIterator[dict]:
    """Agentic chat pipeline: retrieve → synthesize → stream."""

    # Step 1: Retrieval
    yield {"type": "step_update", "phase": 1, "status": "running", "label": "Retrieval"}

    context_chunks = []
    try:
        from mcgill.embeddings.retrieval import hybrid_search
        context_chunks = await hybrid_search(question, top_k=5)
    except Exception:
        try:
            from mcgill.embeddings.retrieval import keyword_search
            context_chunks = await keyword_search(question, top_k=5)
        except Exception:
            pass

    # Also try graph queries for prerequisite questions
    graph_context = ""
    try:
        import re
        codes = re.findall(r"\b([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)\b", question.upper())
        if codes:
            from mcgill.db.neo4j import run_query
            code = f"{codes[0][0]} {codes[0][1]}"
            prereqs = await run_query(
                """MATCH (c:Course {code: $code})-[:PREREQUISITE_OF]->(p:Course)
                   RETURN p.code AS code, p.title AS title""",
                {"code": code},
            )
            if prereqs:
                graph_context = f"\nPrerequisites for {code}: " + ", ".join(
                    f"{r['code']} ({r['title']})" for r in prereqs
                )
    except Exception:
        pass

    yield {"type": "step_update", "phase": 1, "status": "done", "label": "Retrieval"}

    # Build sources list
    sources = []
    for r in context_chunks[:5]:
        sources.append({
            "code": r.get("code", ""),
            "title": r.get("title", ""),
        })

    if sources:
        yield {"type": "sources", "sources": sources}

    # Step 2: Synthesis with Claude
    yield {"type": "step_update", "phase": 2, "status": "running", "label": "Synthesis"}

    # Build context for Claude
    context_text = ""
    for r in context_chunks:
        context_text += f"\n---\n{r.get('code', '')}: {r.get('title', '')}\n{r.get('description', '')}\n"

    if graph_context:
        context_text += graph_context

    try:
        from mcgill.config import settings
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        system_prompt = (
            "You are a McGill University course advisor assistant. "
            "Help students find courses, understand prerequisites, and plan their studies. "
            "Use the provided course data to answer accurately. "
            "Be concise and cite specific course codes when relevant."
        )

        messages = [{"role": "user", "content": f"Context:\n{context_text}\n\nQuestion: {question}"}]

        # Get conversation history
        session = _sessions.get(session_id, {})
        history = session.get("messages", [])[-6:]  # Last 3 exchanges
        if len(history) > 1:
            messages = history[:-1] + messages

        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )

        answer = response.content[0].text
        yield {"type": "assistant", "content": answer}

        _sessions[session_id]["messages"].append({"role": "assistant", "content": answer})

    except Exception as e:
        # Fallback: return context without Claude synthesis
        if context_chunks:
            fallback = "Here are the most relevant courses I found:\n\n"
            for r in context_chunks[:5]:
                fallback += f"**{r.get('code', '')}** — {r.get('title', '')}\n"
                desc = r.get("description", "")
                if desc:
                    fallback += f"{desc[:150]}...\n\n"
            yield {"type": "assistant", "content": fallback}
        else:
            yield {"type": "assistant", "content": f"I couldn't find relevant courses for your query. Error: {e}"}

    yield {"type": "step_update", "phase": 2, "status": "done", "label": "Synthesis"}


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"
