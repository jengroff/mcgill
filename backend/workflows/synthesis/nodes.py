from __future__ import annotations

import logging
import traceback

from typing import Any

from backend.workflows.synthesis.state import SynthesisState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a McGill University course advisor assistant. "
    "Help students find courses, understand prerequisites, and plan their studies. "
    "Use the provided context data to answer accurately and confidently. "
    "When the context contains dates, deadlines, course details, or SQL results, "
    "treat them as authoritative data from the McGill database — state them directly "
    "as facts without hedging, disclaimers, or saying you lack information. "
    "Never say 'I don't have the specific dates' if the context contains dates. "
    "Be concise and cite specific course codes when relevant.\n\n"
    "When department or faculty resources (websites, student societies, library guides, "
    "advisor emails) are available in the context, include the most relevant ones so "
    "students have actionable next steps — not just generic 'contact an advisor' advice.\n\n"
    "For students asking about freshman-year or first-year requirements:\n"
    "- Students entering from outside Quebec's CEGEP system typically must complete a "
    "Foundation Program (30 credits) before the main degree. The Foundation Program "
    "covers biology, chemistry, physics, and mathematics.\n"
    "- If Foundation Year course data is in the context, list the specific courses.\n"
    "- Students with AP Exams, IB, A-Levels, or the French Baccalaureate may receive "
    "exemptions for some or all Foundation courses — always mention this caveat.\n"
    "- Include the foundation year contact email if available in the context.\n"
    "- Link to the Foundation Program page on the McGill Course Catalogue and the "
    "department website when available."
)


def _lookup_dept_websites(dept_codes: set[str]) -> dict[str, str]:
    """Look up department website URLs from the static registry."""
    from backend.services.scraping.faculties import DEPARTMENT_WEBSITES

    return {
        code: DEPARTMENT_WEBSITES[code]
        for code in dept_codes
        if code in DEPARTMENT_WEBSITES
    }


async def context_pack_node(state: SynthesisState) -> dict[str, Any]:
    """Assemble retrieval context into a Claude-ready string."""
    try:
        parts: list[str] = []
        dept_codes: set[str] = set()

        # Course context from retrieval
        for r in state.get("retrieval_context", []):
            parts.append(
                f"{r.get('code', '')}: {r.get('title', '')}\n{r.get('description', '')}"
            )
            code = r.get("code", "")
            if code and " " in code:
                dept_codes.add(code.split()[0])

        # Graph context (prerequisites)
        graph_ctx = state.get("graph_context", "")
        if graph_ctx:
            parts.append(graph_ctx)

        # Plan context (when chat is scoped to a curriculum plan)
        plan_ctx = state.get("plan_context", "")
        if plan_ctx:
            parts.insert(0, plan_ctx)

        # Program guide context (key dates, program requirements, etc.)
        # For each matched chunk, also pull the next few chunks from the same
        # page so the LLM sees continuations (e.g. the Reading Break line that
        # follows the "Classes begin" line on the key-dates page).
        program_parts: list[str] = []
        seen_chunk_ids: set[int] = set()
        program_ctx = state.get("program_context", [])

        if program_ctx:
            from backend.db.postgres import get_pool

            pool = await get_pool()
            for r in program_ctx:
                page_id = r.get("program_page_id")
                chunk_id = r.get("id")
                title = r.get("title", r.get("faculty_slug", ""))
                text = r.get("text", "")

                if not text:
                    continue
                if chunk_id and chunk_id in seen_chunk_ids:
                    continue
                if chunk_id:
                    seen_chunk_ids.add(chunk_id)

                # Fetch this chunk and the next 3 from the same page
                if page_id:
                    async with pool.acquire() as conn:
                        neighbors = await conn.fetch(
                            """SELECT id, text FROM program_chunks
                               WHERE program_page_id = $1
                                 AND chunk_index >= (
                                     SELECT chunk_index FROM program_chunks WHERE id = $2
                                 )
                               ORDER BY chunk_index
                               LIMIT 16""",
                            page_id,
                            chunk_id,
                        )
                    combined = []
                    for nb in neighbors:
                        if nb["id"] not in seen_chunk_ids:
                            seen_chunk_ids.add(nb["id"])
                            combined.append(nb["text"])
                    if combined:
                        program_parts.append(f"[{title}]\n" + "\n".join(combined))
                        continue

                program_parts.append(f"[{title}]\n{text}")

        if program_parts:
            parts[0:0] = program_parts

        # Structured SQL results (counts, aggregates, rankings)
        structured_ctx = state.get("structured_context", "")
        if structured_ctx:
            parts.insert(0, structured_ctx)

        # Department website URLs + resources
        websites = _lookup_dept_websites(dept_codes)
        if websites:
            lines = ["Department websites:"]
            for code, url in sorted(websites.items()):
                lines.append(f"  {code}: {url}")
            parts.append("\n".join(lines))

        # Department and faculty resources (student societies, advisor contacts, etc.)
        from backend.services.scraping.faculties import (
            DEPARTMENT_RESOURCES,
            FACULTY_RESOURCES,
            ALL_FACULTIES,
        )

        resource_lines: list[str] = []
        faculty_slugs: set[str] = set()
        for code in dept_codes:
            if code in DEPARTMENT_RESOURCES:
                res = DEPARTMENT_RESOURCES[code]
                resource_lines.append(f"  {code} resources:")
                for key, val in res.items():
                    resource_lines.append(f"    {key}: {val}")
            for _, slug, prefixes in ALL_FACULTIES:
                if code in prefixes:
                    faculty_slugs.add(slug)

        for slug in faculty_slugs:
            if slug in FACULTY_RESOURCES:
                fac_res = FACULTY_RESOURCES[slug]
                resource_lines.append(f"  Faculty {slug} resources:")
                for key, val in fac_res.items():
                    resource_lines.append(f"    {key}: {val}")

        if resource_lines:
            parts.append("Student resources:\n" + "\n".join(resource_lines))

        # Trim to rough token budget (~12k chars ≈ ~3k tokens)
        context_text = "\n---\n".join(parts)
        if len(context_text) > 12000:
            context_text = context_text[:12000] + "\n... (trimmed)"

        # Store packed context in sources field for downstream
        return {"sources": [{"context_text": context_text}]}
    except Exception as e:
        logger.exception("context_pack_node failed")
        return {
            "sources": [],
            "errors": [f"context_pack: {e}\n{traceback.format_exc()}"],
        }


async def synthesize_node(state: SynthesisState) -> dict[str, Any]:
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
            messages=messages,  # type: ignore[arg-type]
        )

        answer = response.content[0].text  # type: ignore[union-attr]
        return {"response": answer, "status": "complete"}

    except Exception as e:
        logger.exception("synthesize_node failed")
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
