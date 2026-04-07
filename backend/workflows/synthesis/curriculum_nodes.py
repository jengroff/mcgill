from __future__ import annotations

import traceback

from backend.workflows.synthesis.curriculum_state import CurriculumState


async def interest_map_node(state: CurriculumState) -> CurriculumState:
    """Map student interests to department domain tags."""
    try:
        from backend.services.synthesis.curriculum import CurriculumAssembler

        assembler = CurriculumAssembler()
        tags = assembler.map_interests_to_domains(state.get("student_interests", []))
        return {"domain_tags": tags}
    except Exception as e:
        return {
            "domain_tags": [],
            "errors": [f"interest_map: {e}\n{traceback.format_exc()}"],
        }


async def requirements_node(state: CurriculumState) -> CurriculumState:
    """Resolve program requirements from program pages."""
    try:
        from backend.services.synthesis.curriculum import CurriculumAssembler

        assembler = CurriculumAssembler()
        reqs = await assembler.resolve_program_requirements(
            state.get("program_slug", "")
        )
        return {"program_requirements": reqs}
    except Exception as e:
        return {
            "program_requirements": {},
            "errors": [f"requirements: {e}\n{traceback.format_exc()}"],
        }


async def candidate_retrieval_node(state: CurriculumState) -> CurriculumState:
    """Retrieve candidate courses using domain tags as query."""
    try:
        from backend.workflows.retrieval.graph import RetrievalOrchestrator

        query = " ".join(
            state.get("domain_tags", []) + state.get("student_interests", [])
        )
        if not query.strip():
            return {"candidate_courses": []}

        retrieval_orch = RetrievalOrchestrator()
        result = await retrieval_orch.run(query=query, top_k=20, mode="hybrid")
        return {"candidate_courses": result.get("fused_results", [])}  # type: ignore[typeddict-item]
    except Exception as e:
        return {
            "candidate_courses": [],
            "errors": [f"candidate_retrieval: {e}\n{traceback.format_exc()}"],
        }


async def prereq_filter_node(state: CurriculumState) -> CurriculumState:
    """Filter candidates by checking prerequisites are in completed_codes."""
    try:
        from backend.db.neo4j import run_query

        completed = set(state.get("completed_codes", []))
        candidates = state.get("candidate_courses", [])
        filtered: list[dict] = []

        for c in candidates:
            code = c.get("code", "")
            if not code or code in completed:
                continue

            # Check prerequisites
            prereqs = await run_query(
                """MATCH (c:Course {code: $code})-[:PREREQUISITE_OF]->(p:Course)
                   RETURN p.code AS code""",
                {"code": code},
            )
            prereq_codes = {r["code"] for r in prereqs}

            # Include if all prereqs are completed (or no prereqs)
            if prereq_codes <= completed:
                c["prereqs_met"] = True
                filtered.append(c)
            elif len(prereq_codes - completed) <= 1:
                c["prereqs_met"] = False
                c["missing_prereqs"] = list(prereq_codes - completed)
                filtered.append(c)

        return {"candidate_courses": filtered}
    except Exception as e:
        return {"errors": [f"prereq_filter: {e}\n{traceback.format_exc()}"]}


async def conflict_node(state: CurriculumState) -> CurriculumState:
    """Detect restriction conflicts among candidate courses."""
    try:
        from backend.services.synthesis.curriculum import CurriculumAssembler

        assembler = CurriculumAssembler()
        codes = [
            c.get("code", "")
            for c in state.get("candidate_courses", [])
            if c.get("code")
        ]
        conflicts = await assembler.detect_conflicts(codes)
        return {"conflicts": conflicts}
    except Exception as e:
        return {"conflicts": [], "errors": [f"conflict: {e}\n{traceback.format_exc()}"]}


async def rank_node(state: CurriculumState) -> CurriculumState:
    """Score candidates by interest alignment + requirement coverage + prereq readiness."""
    try:
        candidates = state.get("candidate_courses", [])
        requirements = state.get("program_requirements", {})
        domain_tags = set(state.get("domain_tags", []))
        required_codes = set(requirements.get("required", []))
        elective_codes = set(requirements.get("electives", []))
        conflict_codes = {c["source"] for c in state.get("conflicts", [])} | {
            c["target"] for c in state.get("conflicts", [])
        }

        scored: list[dict] = []
        for c in candidates:
            code = c.get("code", "")
            dept = code.split()[0] if code else ""
            score = 0.0

            # Interest alignment
            if dept in domain_tags:
                score += 3.0

            # Requirement coverage
            if code in required_codes:
                score += 5.0
            elif code in elective_codes:
                score += 2.0

            # Prereq readiness
            if c.get("prereqs_met"):
                score += 2.0
            elif c.get("missing_prereqs"):
                score += 0.5

            # Conflict penalty
            if code in conflict_codes:
                score -= 3.0

            # Existing RRF score
            score += c.get("rrf_score", 0.0) * 2

            c["curriculum_score"] = score
            scored.append(c)

        scored.sort(key=lambda x: x["curriculum_score"], reverse=True)
        return {"ranked_courses": scored[:15]}
    except Exception as e:
        return {
            "ranked_courses": state.get("candidate_courses", []),
            "errors": [f"rank: {e}\n{traceback.format_exc()}"],
        }


async def assemble_node(state: CurriculumState) -> CurriculumState:
    """Call Anthropic API to write a natural language curriculum plan."""
    try:
        from backend.config import settings
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        ranked = state.get("ranked_courses", [])
        requirements = state.get("program_requirements", {})
        conflicts = state.get("conflicts", [])
        interests = state.get("student_interests", [])
        completed = state.get("completed_codes", [])

        context = f"""Student interests: {", ".join(interests)}
Completed courses: {", ".join(completed) if completed else "None listed"}
Program requirements: {requirements.get("required", [])}
Available electives: {requirements.get("electives", [])}

Top recommended courses:
"""
        for c in ranked[:10]:
            code = c.get("code", "")
            title = c.get("title", "")
            score = c.get("curriculum_score", 0)
            prereqs_met = c.get("prereqs_met", True)
            missing = c.get("missing_prereqs", [])
            context += (
                f"- {code}: {title} (score: {score:.1f}, prereqs met: {prereqs_met}"
            )
            if missing:
                context += f", missing: {missing}"
            context += ")\n"

        if conflicts:
            context += f"\nRestriction conflicts: {conflicts}\n"

        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=1500,
            system=(
                "You are a McGill University academic advisor. "
                "Create a concise curriculum plan based on the student's interests and program requirements. "
                "Recommend specific courses with their codes, explain why each is recommended, "
                "and note any prerequisite or scheduling considerations."
            ),
            messages=[{"role": "user", "content": context}],
        )

        return {"recommendation": response.content[0].text, "status": "complete"}  # type: ignore[union-attr]
    except Exception:
        # Fallback: generate a simple list
        ranked = state.get("ranked_courses", [])
        fallback = "Recommended courses:\n\n"
        for c in ranked[:10]:
            fallback += f"- **{c.get('code', '')}**: {c.get('title', '')}\n"
        return {"recommendation": fallback, "status": "complete"}
