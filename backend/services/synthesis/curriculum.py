from __future__ import annotations

from backend.services.scraping.faculties import ALL_FACULTIES


# Map keywords → department codes for interest-to-domain matching
_INTEREST_MAP: dict[str, list[str]] = {
    "machine learning": ["COMP", "MATH", "ECSE"],
    "artificial intelligence": ["COMP", "ECSE", "PHIL"],
    "data science": ["COMP", "MATH", "MGCR"],
    "statistics": ["MATH", "EPIB"],
    "biology": ["BIOL", "BIOC", "MICR"],
    "chemistry": ["CHEM", "FDSC"],
    "food chemistry": ["FDSC", "CHEM"],
    "food science": ["FDSC", "LSCI", "ANSC"],
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
                    all_codes = {
                        p for _, _, prefixes in ALL_FACULTIES for p in prefixes
                    }
                    if upper in all_codes:
                        domains.add(upper)
        return sorted(domains)

    async def resolve_program_requirements(self, program_slug: str) -> dict:
        """Query program_pages for required/elective course lists.

        Uses Claude Haiku to extract structured requirements from the
        markdown-formatted program page content.  Falls back to regex
        extraction if the LLM call fails.

        Returns {"required": list[str], "electives": list[str],
                 "categories": dict[str, list[str]], "credits_needed": int}
        """
        from backend.db.postgres import get_pool
        import logging

        logger = logging.getLogger("backend.services.synthesis.curriculum")

        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT title, content FROM program_pages WHERE path LIKE $1",
                f"%{program_slug}%",
            )

        if not rows:
            return {
                "required": [],
                "electives": [],
                "categories": {},
                "credits_needed": 0,
            }

        # Concatenate all matched pages (parent + sub-program pages)
        combined = "\n\n".join(
            f"# {row['title']}\n{row['content']}" for row in rows if row["content"]
        )

        # Try LLM extraction first
        try:
            result = await self._extract_requirements_llm(combined)
            if result.get("required") or result.get("electives"):
                return result
        except Exception as e:
            logger.warning(f"LLM requirement extraction failed: {e}")

        # Fallback: regex-based extraction using markdown section headers
        return self._extract_requirements_regex(combined)

    async def _extract_requirements_llm(self, content: str) -> dict:
        """Use Claude Haiku to extract structured requirements from program page content."""
        import anthropic
        import json as _json
        from backend.config import settings

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        # Truncate to stay within Haiku context limits
        truncated = content[:12000]

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=(
                "You extract program requirements from university course catalog pages. "
                "Return ONLY valid JSON with no other text. The JSON must have these keys:\n"
                '- "required": list of course codes (e.g. ["FDSC 200", "AEMA 310"]) that are required\n'
                '- "electives": list of course codes that are elective/complementary\n'
                '- "categories": dict mapping category names to lists of course codes '
                '(e.g. {"mathematics": ["AEMA 310"], "chemistry": ["FDSC 213", "FDSC 230"]})\n'
                '- "credits_needed": total program credits as an integer\n'
                "Extract course codes exactly as they appear (e.g. FDSC 200, not fdsc200). "
                "Categories should group courses by subject area (mathematics, chemistry, "
                "biology, food science, engineering, etc.)."
            ),
            messages=[{"role": "user", "content": truncated}],
        )

        raw = response.content[0].text.strip()  # type: ignore[union-attr]
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        return _json.loads(raw)  # type: ignore[no-any-return]

    @staticmethod
    def _extract_requirements_regex(content: str) -> dict:
        """Fallback regex extraction using markdown section headings."""
        import re

        required: list[str] = []
        electives: list[str] = []
        code_re = re.compile(r"\b([A-Z]{2,6})\s+(\d{3,4}[A-Z]?)\b")
        credits_re = re.compile(r"\((\d+)\s*credits?\)", re.IGNORECASE)

        credits_needed = 0
        in_required = True
        for line in content.split("\n"):
            lower = line.lower()

            # Use markdown headings to detect section transitions
            if line.startswith("## ") or line.startswith("### "):
                if "elective" in lower or "complementary" in lower:
                    in_required = False
                elif "required" in lower or "core" in lower:
                    in_required = True
                # Try to capture credit total from heading
                cm = credits_re.search(line)
                if cm:
                    credits_needed += int(cm.group(1))

            for m in code_re.finditer(line):
                code = f"{m.group(1)} {m.group(2)}"
                if in_required:
                    required.append(code)
                else:
                    electives.append(code)

        return {
            "required": list(dict.fromkeys(required)),
            "electives": list(dict.fromkeys(electives)),
            "categories": {},
            "credits_needed": credits_needed or len(set(required)) * 3,
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
