from __future__ import annotations

import json
import logging
import tempfile
import traceback
from pathlib import Path

from typing import Any

from backend.workflows.planner.state import PlannerState

logger = logging.getLogger(__name__)


async def gather_context_node(state: PlannerState) -> dict[str, Any]:
    """Gather all context the planning agent needs: program reqs, courses, PDF guide.

    Writes context files to a temp work directory for the SDK agent to read.
    """
    try:
        work_dir = tempfile.mkdtemp(prefix="mcgill_planner_")
        work = Path(work_dir)

        interests = state.get("student_interests", [])
        completed = state.get("completed_codes", [])
        program_slug = state.get("program_slug", "")
        target_semesters = state.get("target_semesters", 4)

        # --- Student profile ---
        profile = {
            "interests": interests,
            "completed_codes": completed,
            "program_slug": program_slug,
            "target_semesters": target_semesters,
        }
        (work / "student_profile.json").write_text(json.dumps(profile, indent=2))

        # --- Program requirements ---
        requirements: dict = {}
        if program_slug:
            from backend.services.synthesis.curriculum import CurriculumAssembler

            assembler = CurriculumAssembler()
            requirements = await assembler.resolve_program_requirements(program_slug)
        (work / "program_requirements.json").write_text(
            json.dumps(requirements, indent=2)
        )

        # --- Candidate courses ---
        candidates = await _fetch_candidate_courses(
            interests, program_slug, requirements
        )
        (work / "candidate_courses.json").write_text(json.dumps(candidates, indent=2))

        # --- PDF guide via VLM (optional) ---
        guide_pages: list[dict] = []
        pdf_bytes = state.get("pdf_bytes")
        if pdf_bytes:
            guide_pages = _process_guide_pdf(
                pdf_bytes,
                state.get("pdf_filename", "guide.pdf"),
            )
            (work / "guide_pages.json").write_text(json.dumps(guide_pages, indent=2))

        return {
            "work_dir": work_dir,
            "program_requirements": requirements,
            "candidate_courses": candidates,
            "guide_pages": guide_pages,
        }
    except Exception as e:
        logger.exception("gather_context failed")
        return {
            "work_dir": state.get("work_dir", ""),
            "errors": [f"gather_context: {e}\n{traceback.format_exc()}"],
        }


async def plan_agent_node(state: PlannerState) -> dict[str, Any]:
    """Run the Claude Agent SDK to build the curriculum plan."""
    work_dir = state.get("work_dir", "")
    if not work_dir:
        return {
            "plan_markdown": "",
            "plan_semesters": [],
            "errors": ["plan_agent: no work_dir from gather_context"],
        }

    try:
        from backend.workflows.planner.prompts import build_planner_prompt

        profile = {
            "interests": state.get("student_interests", []),
            "completed_codes": state.get("completed_codes", []),
            "program_slug": state.get("program_slug", ""),
            "target_semesters": state.get("target_semesters", 4),
        }
        has_guide = bool(state.get("guide_pages"))
        prompt = build_planner_prompt(profile, work_dir, has_guide)

        plan_md, plan_json, messages = await _run_sdk_agent(prompt, work_dir)

        return {
            "plan_markdown": plan_md,
            "plan_semesters": plan_json.get("semesters", []),
            "agent_messages": messages,
            "status": "complete",
        }
    except Exception as e:
        logger.exception("SDK agent failed, falling back to direct synthesis")
        plan_md, plan_semesters = await _fallback_synthesis(state)
        return {
            "plan_markdown": plan_md,
            "plan_semesters": plan_semesters,
            "agent_messages": [],
            "status": "complete",
            "errors": [f"plan_agent: SDK failed ({e}), used fallback"],
        }


async def persist_plan_node(state: PlannerState) -> dict[str, Any]:
    """Persist planner results back to the plans table when plan_id is set."""
    plan_id = state.get("plan_id")
    if not plan_id:
        return {}

    try:
        from backend.db.postgres import get_pool

        pool = await get_pool()
        plan_md = state.get("plan_markdown", "")
        semesters = state.get("plan_semesters", [])

        async with pool.acquire() as conn:
            await conn.execute(
                """UPDATE plans SET plan_markdown = $1, status = 'active', updated_at = now()
                   WHERE id = $2""",
                plan_md,
                plan_id,
            )

            # Replace existing semesters with new ones
            await conn.execute("DELETE FROM plan_semesters WHERE plan_id = $1", plan_id)
            for i, sem in enumerate(semesters):
                courses_list = []
                for c in sem.get("courses", []):
                    if isinstance(c, dict):
                        courses_list.append(c.get("code", ""))
                    else:
                        courses_list.append(str(c))

                total_credits = sem.get("total_credits", 0)
                if not total_credits and isinstance(sem.get("courses"), list):
                    total_credits = sum(
                        c.get("credits", 3)
                        for c in sem["courses"]
                        if isinstance(c, dict)
                    )

                await conn.execute(
                    """INSERT INTO plan_semesters (plan_id, term, sort_order, courses, total_credits)
                       VALUES ($1, $2, $3, $4, $5)""",
                    plan_id,
                    sem.get("term", f"Semester {i + 1}"),
                    i,
                    [c for c in courses_list if c],
                    float(total_credits),
                )

        logger.info("Persisted plan %d with %d semesters", plan_id, len(semesters))
        return {}
    except Exception as e:
        logger.exception("Failed to persist plan %s", plan_id)
        return {"errors": [f"persist_plan: {e}"]}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _fetch_candidate_courses(
    interests: list[str],
    program_slug: str,
    requirements: dict,
) -> list[dict]:
    """Fetch candidate courses via retrieval + direct SQL for breadth."""
    from backend.db.postgres import get_pool
    from backend.services.synthesis.curriculum import CurriculumAssembler

    candidates: list[dict] = []
    seen_codes: set[str] = set()

    # 1. Interest-based retrieval
    if interests:
        assembler = CurriculumAssembler()
        dept_codes = assembler.map_interests_to_domains(interests)

        if dept_codes:
            pool = await get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT code, title, credits, dept, faculty,
                              terms, description, prerequisites_raw,
                              restrictions_raw
                       FROM courses
                       WHERE dept = ANY($1)
                       ORDER BY code
                       LIMIT 200""",
                    dept_codes,
                )
            for r in rows:
                code = r["code"]
                if code not in seen_codes:
                    seen_codes.add(code)
                    candidates.append(
                        {
                            "code": code,
                            "title": r["title"],
                            "credits": float(r["credits"]) if r["credits"] else 3.0,
                            "dept": r["dept"],
                            "faculty": r["faculty"],
                            "terms": r["terms"] or [],
                            "description": (r["description"] or "")[:300],
                            "prerequisites_raw": r["prerequisites_raw"] or "",
                            "restrictions_raw": r["restrictions_raw"] or "",
                        }
                    )

    # 2. Required/elective courses from program
    req_codes = requirements.get("required", []) + requirements.get("electives", [])
    if req_codes:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT code, title, credits, dept, faculty,
                          terms, description, prerequisites_raw,
                          restrictions_raw
                   FROM courses
                   WHERE code = ANY($1)""",
                req_codes,
            )
        for r in rows:
            code = r["code"]
            if code not in seen_codes:
                seen_codes.add(code)
                candidates.append(
                    {
                        "code": code,
                        "title": r["title"],
                        "credits": float(r["credits"]) if r["credits"] else 3.0,
                        "dept": r["dept"],
                        "faculty": r["faculty"],
                        "terms": r["terms"] or [],
                        "description": (r["description"] or "")[:300],
                        "prerequisites_raw": r["prerequisites_raw"] or "",
                        "restrictions_raw": r["restrictions_raw"] or "",
                    }
                )

    return candidates


def _process_guide_pdf(pdf_bytes: bytes, filename: str) -> list[dict]:
    """Process a PDF course guide through the VLM pipeline."""
    from backend.services.vlm.pdf_processor import PDFProcessor

    processor = PDFProcessor(pdf_bytes, filename, use_vlm=True)
    pages = processor.process()
    # Convert PageContent TypedDicts to plain dicts for JSON serialization
    return [dict(p) for p in pages]


async def _run_sdk_agent(prompt: str, work_dir: str) -> tuple[str, dict, list[str]]:
    """Run Claude Agent SDK and return (plan_md, plan_json, messages)."""
    try:
        import claude_agent_sdk as sdk
    except ImportError:
        raise RuntimeError("claude_agent_sdk not installed")

    from backend.config import settings

    messages: list[str] = []

    options = sdk.ClaudeAgentOptions(
        allowed_tools=["Read", "Write", "Glob"],
        model=settings.claude_model,
        env={"ANTHROPIC_API_KEY": settings.anthropic_api_key},
        cwd=work_dir,
    )

    async for message in sdk.query(prompt=prompt, options=options):
        msg_type = getattr(message, "type", None)
        if msg_type == "text" or hasattr(message, "text"):
            text = getattr(message, "text", str(message))
            if text:
                messages.append(text)
        elif hasattr(message, "name"):
            messages.append(f"[tool: {message.name}]")

    # Read output files
    work = Path(work_dir)
    plan_md = ""
    plan_json: dict = {}

    md_path = work / "curriculum_plan.md"
    if md_path.exists():
        plan_md = md_path.read_text()

    json_path = work / "curriculum_plan.json"
    if json_path.exists():
        try:
            plan_json = json.loads(json_path.read_text())
        except json.JSONDecodeError:
            logger.exception("Failed to parse curriculum_plan.json")

    if not plan_md:
        raise RuntimeError("Agent did not produce curriculum_plan.md")

    return plan_md, plan_json, messages


async def _fallback_synthesis(state: PlannerState) -> tuple[str, list[dict]]:
    """Direct Claude API fallback when SDK is unavailable."""
    from backend.config import settings
    import anthropic

    candidates = state.get("candidate_courses", [])
    requirements = state.get("program_requirements", {})
    interests = state.get("student_interests", [])
    completed = state.get("completed_codes", [])
    target = state.get("target_semesters", 4)

    context = f"""Student interests: {", ".join(interests)}
Completed courses: {", ".join(completed) if completed else "None"}
Target: {target} semesters
Program requirements: {json.dumps(requirements, indent=2)}

Available courses ({len(candidates)} total):
"""
    for c in candidates[:50]:
        context += (
            f"- {c['code']}: {c['title']} ({c.get('credits', 3)} cr, "
            f"terms: {c.get('terms', [])}, prereqs: {c.get('prerequisites_raw', 'none')})\n"
        )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=4000,
        system=(
            "You are a McGill University academic advisor. Build a semester-by-semester "
            "curriculum plan. Consider prerequisites, term availability, and credit balance. "
            "Format as markdown with clear semester headings."
        ),
        messages=[{"role": "user", "content": context}],
    )

    plan_md = response.content[0].text  # type: ignore[union-attr]
    return plan_md, []
