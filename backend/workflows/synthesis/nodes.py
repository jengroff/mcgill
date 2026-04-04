"""Synthesis workflow nodes — context packing and Claude synthesis."""

from __future__ import annotations

import traceback

from backend.workflows.synthesis.state import SynthesisState

SYSTEM_PROMPT = (
    "You are a McGill University course advisor assistant. "
    "Help students find courses, understand prerequisites, and plan their studies. "
    "Use the provided course data to answer accurately. "
    "When SQL results are provided in the context, treat them as authoritative data from the database "
    "and use them directly to answer the question — do not say you lack information. "
    "Be concise and cite specific course codes when relevant."
)


async def context_pack_node(state: SynthesisState) -> SynthesisState:
    """Assemble retrieval context into a Claude-ready string."""
    try:
        parts: list[str] = []

        # Course context from retrieval
        for r in state.get("retrieval_context", []):
            parts.append(
                f"{r.get('code', '')}: {r.get('title', '')}\n{r.get('description', '')}"
            )

        # Graph context (prerequisites)
        graph_ctx = state.get("graph_context", "")
        if graph_ctx:
            parts.append(graph_ctx)

        # Structured SQL results (counts, aggregates, rankings)
        structured_ctx = state.get("structured_context", "")
        if structured_ctx:
            parts.insert(0, structured_ctx)  # Prioritize structured data

        # Program guide context
        for r in state.get("program_context", []):
            title = r.get("title", r.get("faculty_slug", ""))
            text = r.get("text", "")
            if text:
                parts.append(f"[{title}]\n{text}")

        # Trim to rough token budget (~8k chars ≈ ~2k tokens)
        context_text = "\n---\n".join(parts)
        if len(context_text) > 8000:
            context_text = context_text[:8000] + "\n... (trimmed)"

        # Store packed context in sources field for downstream
        return {"sources": [{"context_text": context_text}]}
    except Exception as e:
        return {
            "sources": [],
            "errors": [f"context_pack: {e}\n{traceback.format_exc()}"],
        }


async def synthesize_node(state: SynthesisState) -> SynthesisState:
    """Call Anthropic API with system prompt + packed context + conversation history."""
    try:
        from backend.config import settings
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        # Reconstruct context text from packed sources
        context_text = ""
        for s in state.get("sources", []):
            if "context_text" in s:
                context_text = s["context_text"]
                break

        messages = [
            {
                "role": "user",
                "content": f"Context:\n{context_text}\n\nQuestion: {state['query']}",
            }
        ]

        # Prepend conversation history
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

    except Exception as e:
        # Fallback: return context summary without Claude synthesis
        retrieval_ctx = state.get("retrieval_context", [])
        if retrieval_ctx:
            fallback = "Here are the most relevant courses I found:\n\n"
            for r in retrieval_ctx[:5]:
                fallback += f"**{r.get('code', '')}** — {r.get('title', '')}\n"
                desc = r.get("description", "")
                if desc:
                    fallback += f"{desc[:150]}...\n\n"
            return {"response": fallback, "status": "complete"}

        return {
            "response": f"I couldn't find relevant courses for your query. Error: {e}",
            "status": "error",
            "errors": [f"synthesize: {e}\n{traceback.format_exc()}"],
        }
