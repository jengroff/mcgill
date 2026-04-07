from backend.services.scraping.parser import (
    parse_course,
    parse_program_page,
    _table_to_markdown,
    discover_sub_pages,
    extract_variants,
)


def _course_html(
    dept="COMP",
    number="250",
    title="Intro to Computer Science",
    credits="3",
    faculty="Science",
    terms="Fall 2025, Winter 2026",
    prereq="",
    restrict="",
    notes="",
    description="This course covers fundamental concepts in computing.",
):
    parts = ['<div id="contentarea">']
    parts.append(f"<h1>{dept} {number}. {title}.</h1>")
    parts.append(f"<p>Credits: {credits}</p>")
    parts.append(f"<p>Offered by: {faculty}</p>")
    parts.append(f"<p>Terms offered: {terms}</p>")
    if prereq:
        parts.append(f"<p>{prereq}</p>")
    if restrict:
        parts.append(f"<p>{restrict}</p>")
    if notes:
        parts.append(f"<p>{notes}</p>")
    parts.append(f"<p>{description}</p>")
    parts.append("</div>")
    return "\n".join(parts)


class TestParseCourse:
    def test_basic_course(self):
        html = _course_html()
        result = parse_course("comp-250", html, ["Science"])
        assert result is not None
        assert result.code == "COMP 250"
        assert result.dept == "COMP"
        assert result.number == "250"
        assert result.title == "Intro to Computer Science"
        assert result.credits == 3.0
        assert result.faculty == "Science"
        assert "Fall" in result.terms
        assert "Winter" in result.terms

    def test_missing_h1_returns_none(self):
        html = '<div id="contentarea"><p>No heading here</p></div>'
        assert parse_course("comp-250", html, ["Science"]) is None

    def test_empty_html_returns_none(self):
        assert parse_course("comp-250", "", []) is None

    def test_no_content_area_returns_none(self):
        html = "<html><body></body></html>"
        assert parse_course("comp-250", html, []) is None

    def test_extracts_prerequisites(self):
        html = _course_html(prereq="Prerequisite: COMP 202 and MATH 240")
        result = parse_course("comp-250", html, ["Science"])
        assert result is not None
        assert "COMP 202" in result.prerequisites_raw

    def test_extracts_restrictions(self):
        html = _course_html(
            restrict="Restriction: Not open to students who have taken COMP 206"
        )
        result = parse_course("comp-250", html, ["Science"])
        assert result is not None
        assert "COMP 206" in result.restrictions_raw

    def test_extracts_notes(self):
        html = _course_html(notes="Note: This course has a mandatory lab.")
        result = parse_course("comp-250", html, ["Science"])
        assert result is not None
        assert "mandatory lab" in result.notes_raw

    def test_url_constructed_from_slug(self):
        html = _course_html()
        result = parse_course("comp-250", html, ["Science"])
        assert result is not None
        assert (
            result.url
            == "https://coursecatalogue.mcgill.ca/courses/comp-250/index.html"
        )

    def test_extracts_terms(self):
        html = _course_html(terms="Fall 2025")
        result = parse_course("comp-250", html, ["Science"])
        assert result is not None
        assert result.terms == ["Fall"]

    def test_summer_term_extracted(self):
        html = _course_html(terms="Summer 2026")
        result = parse_course("comp-250", html, ["Science"])
        assert result is not None
        assert "Summer" in result.terms

    def test_faculty_from_html_overrides_param(self):
        html = _course_html(faculty="Engineering")
        result = parse_course("comp-250", html, ["Science"])
        assert result is not None
        assert result.faculty == "Engineering"

    def test_credits_parsed_as_float(self):
        html = _course_html(credits="4.5")
        result = parse_course("comp-250", html, ["Science"])
        assert result is not None
        assert result.credits == 4.5

    def test_faculties_list_preserved(self):
        html = _course_html()
        result = parse_course("comp-250", html, ["Science", "Arts"])
        assert result is not None
        assert result.faculties == ["Science", "Arts"]

    def test_description_with_heading(self):
        html = """<div id="contentarea">
            <h1>FDSC 200. Introduction to Food Science.</h1>
            <p>Credits: 3</p>
            <h2>Description</h2>
            <p>An introduction to the physical and chemical properties of food.</p>
        </div>"""
        result = parse_course(
            "fdsc-200", html, ["Agricultural & Environmental Sciences"]
        )
        assert result is not None
        assert "physical and chemical properties" in result.description


class TestParseProgramPage:
    def test_extracts_title(self):
        html = '<div id="contentarea"><h1>Food Science Option B.Sc.</h1><p>Program requirements follow.</p></div>'
        title, _ = parse_program_page(html)
        assert title == "Food Science Option B.Sc."

    def test_preserves_section_headings(self):
        html = """<div id="contentarea">
            <h1>Food Science</h1>
            <h2>Required Courses</h2>
            <p>Students must complete the following courses.</p>
            <h3>Elective Courses</h3>
            <p>Choose from the following electives.</p>
        </div>"""
        _, content = parse_program_page(html)
        assert "## Required Courses" in content
        assert "### Elective Courses" in content

    def test_converts_tables_to_markdown(self):
        html = """<div id="contentarea">
            <h1>Program</h1>
            <table>
                <tr><th>Course</th><th>Credits</th></tr>
                <tr><td>FDSC 200</td><td>3</td></tr>
                <tr><td>FDSC 251</td><td>3</td></tr>
            </table>
        </div>"""
        _, content = parse_program_page(html)
        assert "| Course | Credits |" in content
        assert "| FDSC 200 | 3 |" in content
        assert "| FDSC 251 | 3 |" in content

    def test_empty_html_returns_empty(self):
        title, content = parse_program_page("")
        assert title == ""
        assert content == ""

    def test_skips_short_paragraphs(self):
        html = """<div id="contentarea">
            <h1>Program</h1>
            <p>Short.</p>
            <p>This is a paragraph that is long enough to be included in the output content for chunking.</p>
        </div>"""
        _, content = parse_program_page(html)
        assert "Short." not in content
        assert "long enough" in content


class TestTableToMarkdown:
    def test_basic_table(self):
        from bs4 import BeautifulSoup

        html = (
            "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
        )
        table = BeautifulSoup(html, "html.parser").find("table")
        md = _table_to_markdown(table)
        assert "| A | B |" in md
        assert "| --- | --- |" in md
        assert "| 1 | 2 |" in md

    def test_skips_single_wide_cell_rows(self):
        from bs4 import BeautifulSoup

        html = """<table>
            <tr><th>Course</th><th>Credits</th></tr>
            <tr><td>COMP 250</td><td>3</td></tr>
            <tr><td>This is an expanded description row that spans the whole table</td></tr>
        </table>"""
        table = BeautifulSoup(html, "html.parser").find("table")
        md = _table_to_markdown(table)
        assert "expanded description" not in md
        assert "COMP 250" in md

    def test_empty_table_returns_empty(self):
        from bs4 import BeautifulSoup

        html = "<table></table>"
        table = BeautifulSoup(html, "html.parser").find("table")
        assert _table_to_markdown(table) == ""

    def test_pipe_in_cell_escaped(self):
        from bs4 import BeautifulSoup

        html = "<table><tr><th>Name</th></tr><tr><td>A | B</td></tr></table>"
        table = BeautifulSoup(html, "html.parser").find("table")
        md = _table_to_markdown(table)
        assert "A / B" in md

    def test_pads_short_rows(self):
        from bs4 import BeautifulSoup

        html = (
            "<table><tr><th>A</th><th>B</th><th>C</th></tr><tr><td>1</td></tr></table>"
        )
        table = BeautifulSoup(html, "html.parser").find("table")
        md = _table_to_markdown(table)
        lines = md.strip().split("\n")
        # Data row should be padded to 3 columns
        assert lines[-1].count("|") == 4  # leading + 3 separators


class TestDiscoverSubPages:
    def test_finds_child_links(self):
        html = """<div id="contentarea">
            <a href="/en/undergrad/science/programs/biology/">Biology</a>
            <a href="/en/undergrad/science/programs/chemistry/">Chemistry</a>
        </div>"""
        result = discover_sub_pages(html, "/en/undergrad/science/programs")
        assert "/en/undergrad/science/programs/biology/" in result
        assert "/en/undergrad/science/programs/chemistry/" in result

    def test_ignores_parent_link(self):
        html = """<div id="contentarea">
            <a href="/en/undergrad/science/programs/">Programs</a>
            <a href="/en/undergrad/science/programs/bio/">Bio</a>
        </div>"""
        result = discover_sub_pages(html, "/en/undergrad/science/programs")
        assert "/en/undergrad/science/programs/" not in result
        assert "/en/undergrad/science/programs/bio/" in result

    def test_ignores_external_links(self):
        html = """<div id="contentarea">
            <a href="https://example.com/other">External</a>
            <a href="/en/other/path/">Other section</a>
        </div>"""
        result = discover_sub_pages(html, "/en/undergrad/science/programs")
        assert len(result) == 0

    def test_deduplicates(self):
        html = """<div id="contentarea">
            <a href="/en/programs/bio/">Bio</a>
            <a href="/en/programs/bio">Bio again</a>
        </div>"""
        result = discover_sub_pages(html, "/en/programs")
        assert len(result) == 1

    def test_normalizes_trailing_slash(self):
        html = """<div id="contentarea">
            <a href="/en/programs/bio">Bio</a>
        </div>"""
        result = discover_sub_pages(html, "/en/programs/")
        assert result == ["/en/programs/bio/"]

    def test_empty_page_returns_empty(self):
        assert discover_sub_pages("", "/en/programs") == []


class TestExtractVariants:
    def test_extracts_known_codes_from_prereq_context(self):
        html = """<div id="contentarea">
            <p>Prerequisite: COMP 202 and MATH 240 or permission of instructor.</p>
        </div>"""
        known = {"COMP 202", "MATH 240", "COMP 250"}
        result = extract_variants(html, known)
        assert "COMP 202" in result
        assert "MATH 240" in result

    def test_ignores_unknown_codes(self):
        html = """<div id="contentarea">
            <p>Prerequisite: FAKE 999</p>
        </div>"""
        result = extract_variants(html, {"COMP 250"})
        assert len(result) == 0

    def test_required_course_context(self):
        html = """<div id="contentarea">
            <p>Required course FDSC 200 must be completed before registration.</p>
        </div>"""
        result = extract_variants(html, {"FDSC 200"})
        assert "FDSC 200" in result

    def test_corequisite_context(self):
        html = """<div id="contentarea">
            <p>Corequisite: MATH 141</p>
        </div>"""
        result = extract_variants(html, {"MATH 141"})
        assert "MATH 141" in result
