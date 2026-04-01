"""Curriculum assembly service — interest mapping, requirements, conflict detection."""

from __future__ import annotations

from backend.services.scraping.faculties import ALL_FACULTIES


# Map keywords → department codes for interest-to-domain matching
_INTEREST_MAP: dict[str, list[str]] = {
    "machine learning": ["COMP", "MATH", "ECSE"],
    "artificial intelligence": ["COMP", "ECSE", "PHIL"],
    "data science": ["COMP", "MATH", "MGCR"],
    "statistics": ["MATH", "EPIB"],
    "biology": ["BIOL", "BIOC", "MICR"],
    "chemistry": ["CHEM"],
    "physics": ["PHYS", "MATH"],
    "mathematics": ["MATH"],
    "computer science": ["COMP"],
    "software engineering": ["COMP", "ECSE"],
    "electrical engineering": ["ECSE"],
    "mechanical engineering": ["MECH"],
    "civil engineering": ["CIVE"],
    "chemical engineering": ["CHEE"],
    "economics": ["ECON", "MATH"],
    "finance": ["FINE", "ECON", "MATH"],
    "management": ["MGCR", "MGMT", "FINE"],
    "psychology": ["PSYC", "NSCI"],
    "neuroscience": ["NSCI", "PSYC", "BIOL"],
    "linguistics": ["LING", "COMP"],
    "philosophy": ["PHIL"],
    "political science": ["POLI"],
    "history": ["HIST"],
    "music": ["MUAR", "MUSP", "MUTH"],
    "environment": ["ENVR", "ENVB", "GEOG"],
    "geography": ["GEOG", "ENVR"],
}


class CurriculumAssembler:
    def map_interests_to_domains(self, interests: list[str]) -> list[str]:
        """Map free-text interests to canonical department codes."""
        domains: set[str] = set()
        for interest in interests:
            key = interest.lower().strip()
            if key in _INTEREST_MAP:
                domains.update(_INTEREST_MAP[key])
            else:
                # Fuzzy match: check if interest substring matches any key
                for map_key, codes in _INTEREST_MAP.items():
                    if key in map_key or map_key in key:
                        domains.update(codes)
                        break
                else:
                    # Try matching against department codes directly
                    upper = key.upper()
                    all_codes = {p for _, _, prefixes in ALL_FACULTIES for p in prefixes}
                    if upper in all_codes:
                        domains.add(upper)
        return sorted(domains)

    async def resolve_program_requirements(self, program_slug: str) -> dict:
        """Query program_pages for required/elective course lists.

        Returns {"required": list[str], "electives": list[str], "credits_needed": int}
        """
        from backend.db.postgres import get_pool
        import re

        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT title, content FROM program_pages WHERE path LIKE $1",
                f"%{program_slug}%",
            )

        required: list[str] = []
        electives: list[str] = []
        code_re = re.compile(r"\b([A-Z]{2,6})\s+(\d{3,4}[A-Z]?)\b")

        for row in rows:
            content = row["content"] or ""
            # Simple heuristic: codes in "required" sections vs "elective" sections
            in_required = True
            for line in content.split("\n"):
                lower = line.lower()
                if "elective" in lower or "complementary" in lower:
                    in_required = False
                elif "required" in lower or "core" in lower:
                    in_required = True

                for m in code_re.finditer(line):
                    code = f"{m.group(1)} {m.group(2)}"
                    if in_required:
                        required.append(code)
                    else:
                        electives.append(code)

        return {
            "required": list(dict.fromkeys(required)),
            "electives": list(dict.fromkeys(electives)),
            "credits_needed": len(set(required)) * 3,  # rough estimate
        }

    async def detect_conflicts(self, course_codes: list[str]) -> list[dict]:
        """Query Neo4j for restriction violations among selected courses."""
        if not course_codes:
            return []

        from backend.db.neo4j import run_query

        conflicts = await run_query(
            """UNWIND $codes AS code
               MATCH (c:Course {code: code})-[:RESTRICTED_WITH]->(r:Course)
               WHERE r.code IN $codes
               RETURN c.code AS source, r.code AS target, 'RESTRICTED_WITH' AS type""",
            {"codes": course_codes},
        )
        return [dict(c) for c in conflicts]
