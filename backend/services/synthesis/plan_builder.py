"""Plan auto-population — extract program requirements and distribute across semesters."""

from __future__ import annotations

import logging
import re

from backend.services.synthesis.curriculum import CurriculumAssembler

logger = logging.getLogger(__name__)


class PlanBuilder:
    async def auto_populate(
        self,
        program_slug: str,
        start_term: str | None,
        target_semesters: int,
        completed_codes: list[str],
    ) -> list[dict]:
        """Build pre-populated semester dicts from scraped program requirements.

        Extracts course codes from `program_pages` via regex (no LLM),
        looks up credits and term availability from the `courses` table,
        and distributes courses across the requested number of semesters.

        Returns a list of dicts ready for insertion into `plan_semesters`:
        `[{"term": str, "sort_order": int, "courses": list[str], "total_credits": float}]`
        """
        requirements = await self._get_requirements(program_slug)
        all_codes = requirements.get("required", []) + requirements.get("electives", [])

        completed_set = {c.upper().strip() for c in completed_codes}
        all_codes = [c for c in all_codes if c not in completed_set]

        if not all_codes:
            return self._empty_semesters(start_term, target_semesters)

        course_info = await self._lookup_courses(all_codes)
        term_sequence = self._generate_term_sequence(start_term, target_semesters)
        return self._distribute_courses(all_codes, course_info, term_sequence)

    async def _get_requirements(self, program_slug: str) -> dict:
        from backend.db.postgres import get_pool

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

        combined = "\n\n".join(
            f"# {r['title']}\n{r['content']}" for r in rows if r["content"]
        )
        return CurriculumAssembler._extract_requirements_regex(combined)

    async def _lookup_courses(self, codes: list[str]) -> dict[str, dict]:
        from backend.db.postgres import get_pool

        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT code, title, credits, terms FROM courses WHERE code = ANY($1)",
                codes,
            )
        return {
            r["code"]: {
                "title": r["title"],
                "credits": float(r["credits"]) if r["credits"] else 3.0,
                "terms": r["terms"] or [],
            }
            for r in rows
        }

    @staticmethod
    def _generate_term_sequence(start_term: str | None, count: int) -> list[str]:
        if not start_term:
            return [f"Semester {i + 1}" for i in range(count)]

        match = re.match(r"(Fall|Winter|Summer)\s+(\d{4})", start_term, re.IGNORECASE)
        if not match:
            return [f"Semester {i + 1}" for i in range(count)]

        season = match.group(1).capitalize()
        year = int(match.group(2))

        terms: list[str] = []
        for _ in range(count):
            terms.append(f"{season} {year}")
            if season == "Fall":
                season = "Winter"
                year += 1
            elif season == "Winter":
                season = "Fall"
            else:
                season = "Fall"
        return terms

    @staticmethod
    def _distribute_courses(
        codes: list[str],
        course_info: dict[str, dict],
        term_sequence: list[str],
        max_per_semester: int = 5,
    ) -> list[dict]:
        # Sort by course number so lower-level courses land in earlier semesters
        def sort_key(code: str) -> tuple[int, str]:
            parts = code.split()
            num = int(re.sub(r"[^0-9]", "", parts[1])) if len(parts) > 1 else 0
            return (num, code)

        sorted_codes = sorted(codes, key=sort_key)

        # Build semester buckets
        semesters: list[dict] = []
        for i, term in enumerate(term_sequence):
            semesters.append(
                {
                    "term": term,
                    "sort_order": i,
                    "courses": [],
                    "total_credits": 0.0,
                }
            )

        # Determine each semester's season
        def get_season(term: str) -> str:
            t = term.split()[0].capitalize()
            return t if t in ("Fall", "Winter", "Summer") else ""

        semester_seasons = [get_season(s["term"]) for s in semesters]

        # Assign courses
        for code in sorted_codes:
            info = course_info.get(code)
            if not info:
                continue

            available = [t.split()[0].capitalize() for t in info["terms"]]
            credits = info["credits"]

            best_idx = None
            for i, sem in enumerate(semesters):
                if len(sem["courses"]) >= max_per_semester:
                    continue
                season = semester_seasons[i]
                if not season or not available or season in available:
                    best_idx = i
                    break

            if best_idx is not None:
                semesters[best_idx]["courses"].append(code)
                semesters[best_idx]["total_credits"] += credits

        return semesters

    @staticmethod
    def _empty_semesters(start_term: str | None, count: int) -> list[dict]:
        terms = PlanBuilder._generate_term_sequence(start_term, count)
        return [
            {"term": t, "sort_order": i, "courses": [], "total_credits": 0.0}
            for i, t in enumerate(terms)
        ]
