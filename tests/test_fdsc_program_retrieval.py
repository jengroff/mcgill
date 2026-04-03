"""Integration tests for FDSC program requirement retrieval.

These tests run against the live Docker postgres database and verify that
the retrieval and synthesis pipelines can answer department-specific
program requirement questions — the use case that prompted the sub-page
scraping and structured parsing work.

Requires: `make db` (postgres + neo4j running), FDSC data scraped.
"""

import re

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Data presence — the sub-program pages must be in the DB
# ---------------------------------------------------------------------------


class TestFDSCDataPresence:
    """Verify the scraped FDSC program pages are in postgres with
    structured markdown content (tables, section headings)."""

    async def test_fdsc_courses_exist(self, db):
        async with db.acquire() as conn:
            count = await conn.fetchval(
                "SELECT count(*) FROM courses WHERE dept = 'FDSC'"
            )
        assert count >= 20, f"Expected 20+ FDSC courses, got {count}"

    async def test_fdsc_subprogram_pages_exist(self, db):
        async with db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT path, title FROM program_pages "
                "WHERE path LIKE '%food-science-agricultural-chemistry/%' "
                "AND path != '/en/undergraduate/agri-env-sci/programs/food-science-agricultural-chemistry/' "
                "AND path NOT LIKE '%/en/graduate/%'"
            )
        paths = [r["path"] for r in rows]
        assert len(paths) >= 5, f"Expected 5+ FDSC sub-program pages, got {len(paths)}: {paths}"

    async def test_food_science_option_has_required_courses_table(self, db):
        async with db.acquire() as conn:
            content = await conn.fetchval(
                "SELECT content FROM program_pages "
                "WHERE path LIKE '%food-science-option-bsc-fsc%'"
            )
        assert content is not None, "Food Science Option page not found"
        assert "## Required Courses" in content, "Missing '## Required Courses' heading"
        assert "| Course | Title | Credits |" in content, "Missing markdown table header"
        assert "AEMA 310" in content, "Missing AEMA 310 in required courses"

    async def test_food_chemistry_option_has_required_courses_table(self, db):
        async with db.acquire() as conn:
            content = await conn.fetchval(
                "SELECT content FROM program_pages "
                "WHERE path LIKE '%food-science-chemistry-option%'"
            )
        assert content is not None, "Food Chemistry Option page not found"
        assert "## Required Courses" in content
        assert "FDSC 213" in content, "Missing FDSC 213 (Analytical Chemistry)"

    async def test_program_pages_have_embeddings(self, db):
        async with db.acquire() as conn:
            count = await conn.fetchval(
                "SELECT count(*) FROM program_chunks pc "
                "JOIN program_pages pp ON pp.id = pc.program_page_id "
                "WHERE pp.path LIKE '%food-science-agricultural-chemistry/%' "
                "AND pc.embedding IS NOT NULL"
            )
        assert count >= 20, f"Expected 20+ embedded FDSC program chunks, got {count}"


# ---------------------------------------------------------------------------
# Structured SQL retrieval — text-to-SQL should query program_pages
# ---------------------------------------------------------------------------


class TestStructuredRetrieval:
    """The structured_node uses Claude Haiku to generate SQL. Verify that
    direct SQL queries against program_pages return FDSC requirement data."""

    async def test_sql_finds_fdsc_required_courses(self, db):
        """A manually-written SQL query can find required courses from
        program_pages content — this is what Haiku should generate."""
        async with db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT title, content FROM program_pages "
                "WHERE content ILIKE '%Required Courses%' "
                "AND path LIKE '%food-science-agricultural-chemistry/%'"
            )
        assert len(rows) >= 3, f"Expected 3+ pages with required courses, got {len(rows)}"
        # Verify the content contains course codes in tables
        all_content = " ".join(r["content"] for r in rows)
        codes = re.findall(r"\b(FDSC \d{3}[A-Z]?\d?)\b", all_content)
        assert len(codes) >= 10, f"Expected 10+ FDSC course codes in requirements, got {len(codes)}"

    async def test_sql_finds_math_related_courses_in_fdsc(self, db):
        """Verify the program pages mention math/stats courses that are
        required for FDSC programs."""
        async with db.acquire() as conn:
            content = await conn.fetchval(
                "SELECT string_agg(content, ' ') FROM program_pages "
                "WHERE path LIKE '%food-science-agricultural-chemistry/%'"
            )
        assert content is not None
        # AEMA 310 (Statistical Methods) should appear in requirements
        assert "AEMA 310" in content, "AEMA 310 (Statistical Methods) not found"

    async def test_sql_can_cross_reference_program_and_courses(self, db):
        """Join program_pages content with courses table to find details
        about required courses."""
        async with db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT c.code, c.title, c.credits, c.prerequisites_raw "
                "FROM courses c "
                "WHERE c.code IN ('AEMA 310', 'FDSC 213', 'LSCI 211', 'FDSC 233')"
            )
        codes = {r["code"] for r in rows}
        assert "AEMA 310" in codes, "AEMA 310 not in courses table"
        assert "FDSC 213" in codes, "FDSC 213 not in courses table"


# ---------------------------------------------------------------------------
# Retrieval pipeline integration
# ---------------------------------------------------------------------------


class TestRetrievalPipeline:
    """Run the full RetrievalOrchestrator and verify program requirement
    data surfaces for FDSC queries."""

    async def test_retrieval_finds_fdsc_program_context(self):
        from backend.workflows.retrieval.graph import RetrievalOrchestrator

        orch = RetrievalOrchestrator()
        result = await orch.run(query="FDSC food science program required courses")

        program_results = result.get("program_results", [])
        assert len(program_results) > 0, "No program results returned"
        combined = " ".join(str(r) for r in program_results)
        assert "food science" in combined.lower(), (
            f"Program results don't mention food science: {combined[:200]}"
        )

    async def test_retrieval_structured_node_returns_content(self):
        from backend.workflows.retrieval.graph import RetrievalOrchestrator

        orch = RetrievalOrchestrator()
        result = await orch.run(
            query="what math or statistics courses are required for the FDSC food science program"
        )

        structured = result.get("structured_context", "")
        # structured_node may return SQL results or empty string; either is OK
        # but fused_results + program_results should have data
        fused = result.get("fused_results", [])
        program = result.get("program_results", [])
        assert len(fused) > 0 or len(program) > 0 or structured, (
            "Retrieval returned no results at all for FDSC math query"
        )

    async def test_retrieval_keyword_finds_fdsc_courses(self):
        from backend.workflows.retrieval.graph import RetrievalOrchestrator

        orch = RetrievalOrchestrator()
        result = await orch.run(query="FDSC analytical chemistry food science")

        fused = result.get("fused_results", [])
        codes = [r.get("code", "") for r in fused]
        assert any("FDSC" in c for c in codes), (
            f"No FDSC courses in fused results: {codes}"
        )


# ---------------------------------------------------------------------------
# Synthesis pipeline — end-to-end answer quality
# ---------------------------------------------------------------------------


class TestSynthesisPipeline:
    """Run retrieval + synthesis and verify the final answer references
    actual FDSC program requirement data."""

    async def test_synthesis_answers_fdsc_required_courses(self):
        """Ask about required courses for FDSC — should retrieve the program
        page data and list actual course codes rather than punting to the
        department website."""
        from backend.workflows.retrieval.graph import RetrievalOrchestrator
        from backend.workflows.synthesis.graph import SynthesisOrchestrator

        query = "what are the required courses for the FDSC food science program"
        retrieval = RetrievalOrchestrator()
        retrieval_state = await retrieval.run(query=query)

        synthesis = SynthesisOrchestrator()
        result = await synthesis.run(
            query=query,
            retrieval_context=retrieval_state.get("fused_results", []),
            program_context=retrieval_state.get("program_results", []),
            graph_context=retrieval_state.get("graph_context", ""),
            structured_context=retrieval_state.get("structured_context", ""),
        )

        answer = result.get("response", "")
        assert len(answer) > 50, f"Answer too short: {answer}"
        # Should mention at least some FDSC course codes
        fdsc_mentions = len([c for c in ["FDSC", "AEMA", "LSCI", "BREE"] if c in answer])
        assert fdsc_mentions >= 1, (
            f"Answer doesn't reference any FDSC-related course codes: {answer[:300]}"
        )

    async def test_synthesis_answers_fdsc_chemistry_courses(self):
        from backend.workflows.retrieval.graph import RetrievalOrchestrator
        from backend.workflows.synthesis.graph import SynthesisOrchestrator

        retrieval = RetrievalOrchestrator()
        retrieval_state = await retrieval.run(
            query="which FDSC courses are foundational chemistry, not food-related"
        )

        synthesis = SynthesisOrchestrator()
        result = await synthesis.run(
            query="which FDSC courses are foundational chemistry, not food-related",
            retrieval_context=retrieval_state.get("fused_results", []),
            program_context=retrieval_state.get("program_results", []),
            graph_context=retrieval_state.get("graph_context", ""),
            structured_context=retrieval_state.get("structured_context", ""),
        )

        answer = result.get("response", "")
        assert len(answer) > 50, f"Answer too short: {answer}"
        # Should mention at least one of the chemistry courses
        chem_codes = ["FDSC 213", "FDSC 230", "FDSC 231", "FDSC 233"]
        found = [c for c in chem_codes if c in answer]
        assert len(found) >= 1, (
            f"Answer doesn't reference any FDSC chemistry courses {chem_codes}: {answer[:300]}"
        )

    async def test_synthesis_answers_food_science_option_requirements(self):
        from backend.workflows.retrieval.graph import RetrievalOrchestrator
        from backend.workflows.synthesis.graph import SynthesisOrchestrator

        query = "list the required courses for the FDSC Food Science Option B.Sc. program"
        retrieval = RetrievalOrchestrator()
        retrieval_state = await retrieval.run(query=query)

        synthesis = SynthesisOrchestrator()
        result = await synthesis.run(
            query=query,
            retrieval_context=retrieval_state.get("fused_results", []),
            program_context=retrieval_state.get("program_results", []),
            graph_context=retrieval_state.get("graph_context", ""),
            structured_context=retrieval_state.get("structured_context", ""),
        )

        answer = result.get("response", "")
        assert len(answer) > 100, f"Answer too short: {answer}"
        # Should mention at least some known required courses
        expected = ["FDSC 200", "FDSC 251", "FDSC 442", "BREE 324",
                    "FDSC 213", "LSCI 211", "AEMA 310", "FDSC 330"]
        found = [c for c in expected if c in answer]
        assert len(found) >= 2, (
            f"Answer only mentions {found} of expected {expected}: {answer[:400]}"
        )


# ---------------------------------------------------------------------------
# Curriculum requirement extraction
# ---------------------------------------------------------------------------


class TestCurriculumExtraction:
    """Test the CurriculumAssembler requirement extraction against
    the FDSC program pages in the database."""

    async def test_regex_extraction_finds_fdsc_requirements(self, db):
        from backend.services.synthesis.curriculum import CurriculumAssembler

        async with db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT title, content FROM program_pages "
                "WHERE path LIKE '%food-science-option-bsc-fsc%'"
            )
        content = "\n\n".join(
            f"# {r['title']}\n{r['content']}" for r in rows if r["content"]
        )
        ca = CurriculumAssembler()
        result = ca._extract_requirements_regex(content)

        assert len(result["required"]) >= 10, (
            f"Expected 10+ required courses, got {result['required']}"
        )
        assert "AEMA 310" in result["required"], "AEMA 310 not in required"
        assert "FDSC 200" in result["required"], "FDSC 200 not in required"
        assert result["credits_needed"] > 0, "credits_needed should be > 0"

    async def test_llm_extraction_returns_structured_json(self, db):
        """Run the full LLM extraction (Claude Haiku) against FDSC content."""
        from backend.services.synthesis.curriculum import CurriculumAssembler

        async with db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT title, content FROM program_pages "
                "WHERE path LIKE '%food-science-option-bsc-fsc%'"
            )
        content = "\n\n".join(
            f"# {r['title']}\n{r['content']}" for r in rows if r["content"]
        )
        ca = CurriculumAssembler()
        result = await ca._extract_requirements_llm(content)

        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert "required" in result, f"Missing 'required' key: {result.keys()}"
        assert len(result["required"]) >= 10, (
            f"Expected 10+ required courses, got {result['required']}"
        )
        assert any("FDSC" in c for c in result["required"]), (
            f"No FDSC codes in required: {result['required']}"
        )

    async def test_resolve_program_requirements_end_to_end(self, db):
        from backend.services.synthesis.curriculum import CurriculumAssembler

        ca = CurriculumAssembler()
        result = await ca.resolve_program_requirements("food-science-option-bsc-fsc")

        assert len(result["required"]) >= 10, (
            f"Expected 10+ required courses: {result['required']}"
        )
        assert "FDSC 200" in result["required"]
