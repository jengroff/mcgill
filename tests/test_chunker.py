from backend.services.embedding.chunker import (
    split_sentences,
    chunk_course,
    chunk_program_page,
)


class TestSplitSentences:
    def test_splits_on_period(self):
        result = split_sentences("First sentence. Second sentence. Third.")
        assert len(result) == 3
        assert result[0] == "First sentence."
        assert result[1] == "Second sentence."

    def test_splits_on_exclamation(self):
        result = split_sentences("Wow! Amazing! Incredible.")
        assert len(result) == 3

    def test_splits_on_question_mark(self):
        result = split_sentences("Who? What? Where.")
        assert len(result) == 3

    def test_empty_string(self):
        assert split_sentences("") == []

    def test_whitespace_only(self):
        assert split_sentences("   ") == []

    def test_single_sentence(self):
        result = split_sentences("Just one sentence.")
        assert result == ["Just one sentence."]

    def test_strips_whitespace(self):
        result = split_sentences("  First.   Second.  ")
        assert result[0] == "First."
        assert result[1] == "Second."


class TestChunkCourse:
    def test_single_chunk_for_short_description(self):
        chunks = chunk_course(
            code="COMP 250",
            title="Intro to CS",
            description="A short description.",
        )
        assert len(chunks) == 1
        assert "Course: COMP 250" in chunks[0]
        assert "A short description." in chunks[0]

    def test_prefix_includes_faculty_and_dept(self):
        chunks = chunk_course(
            code="COMP 250",
            title="Intro to CS",
            description="A short description.",
            dept="COMP",
            faculty="Science",
        )
        assert "Faculty: Science" in chunks[0]
        assert "Department: COMP" in chunks[0]

    def test_includes_prerequisites(self):
        chunks = chunk_course(
            code="COMP 250",
            title="Intro to CS",
            description="Main content here.",
            prerequisites_raw="COMP 202",
        )
        full = " ".join(chunks)
        assert "Prerequisites: COMP 202" in full

    def test_includes_restrictions(self):
        chunks = chunk_course(
            code="COMP 250",
            title="Intro to CS",
            description="Main content.",
            restrictions_raw="Not open to COMP majors",
        )
        full = " ".join(chunks)
        assert "Restrictions: Not open to COMP majors" in full

    def test_includes_notes(self):
        chunks = chunk_course(
            code="COMP 250",
            title="Intro to CS",
            description="Main content.",
            notes_raw="Lab required",
        )
        full = " ".join(chunks)
        assert "Notes: Lab required" in full

    def test_windowing_produces_multiple_chunks(self):
        sentences = ". ".join(f"Sentence {i}" for i in range(10)) + "."
        chunks = chunk_course(
            code="COMP 250",
            title="Intro",
            description=sentences,
            window_size=3,
            overlap=1,
        )
        assert len(chunks) > 1

    def test_overlap_shares_sentences(self):
        sentences = "First. Second. Third. Fourth. Fifth."
        chunks = chunk_course(
            code="COMP 250",
            title="Intro",
            description=sentences,
            window_size=2,
            overlap=1,
        )
        assert len(chunks) >= 2
        # Second chunk should start with a sentence from the first chunk
        # (due to overlap)
        assert "Second." in chunks[0]
        assert "Second." in chunks[1]

    def test_empty_description_returns_prefix_only(self):
        chunks = chunk_course(code="COMP 250", title="Intro", description="")
        assert len(chunks) == 1
        assert "Course: COMP 250" in chunks[0]

    def test_every_chunk_has_prefix(self):
        sentences = ". ".join(f"Sentence {i}" for i in range(10)) + "."
        chunks = chunk_course(
            code="COMP 250",
            title="Intro",
            description=sentences,
            window_size=3,
            overlap=1,
        )
        for chunk in chunks:
            assert chunk.startswith("Course: COMP 250")


class TestChunkProgramPage:
    def test_single_chunk_for_short_content(self):
        chunks = chunk_program_page(
            title="Food Science Option",
            content="A short program description.",
            faculty_slug="agri-env-sci",
        )
        assert len(chunks) == 1
        assert "Program: Food Science Option" in chunks[0]
        assert "Faculty: agri-env-sci" in chunks[0]

    def test_windowing_for_long_content(self):
        sentences = ". ".join(f"Requirement {i}" for i in range(10)) + "."
        chunks = chunk_program_page(
            title="Program",
            content=sentences,
            faculty_slug="science",
            window_size=3,
            overlap=1,
        )
        assert len(chunks) > 1

    def test_empty_title_and_content_returns_empty(self):
        chunks = chunk_program_page(title="", content="", faculty_slug="science")
        assert chunks == []

    def test_empty_content_with_title_returns_prefix(self):
        chunks = chunk_program_page(
            title="Some Program", content="", faculty_slug="science"
        )
        assert len(chunks) == 1
        assert "Program: Some Program" in chunks[0]
