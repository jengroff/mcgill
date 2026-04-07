from backend.services.scraping.faculties import (
    ALL_FACULTIES,
    PROGRAM_PAGES,
    DEPARTMENT_WEBSITES,
    DEPARTMENT_RESOURCES,
    FACULTY_RESOURCES,
    get_active_faculties,
)
from backend.services.synthesis.curriculum import CurriculumAssembler


class TestAllFaculties:
    def test_has_entries(self):
        assert len(ALL_FACULTIES) >= 5

    def test_entry_structure(self):
        for name, slug, dept_codes in ALL_FACULTIES:
            assert isinstance(name, str) and len(name) > 0
            assert isinstance(slug, str) and len(slug) > 0
            assert isinstance(dept_codes, list) and len(dept_codes) > 0

    def test_no_duplicate_slugs(self):
        slugs = [slug for _, slug, _ in ALL_FACULTIES]
        assert len(slugs) == len(set(slugs))

    def test_dept_codes_are_uppercase(self):
        for _, _, codes in ALL_FACULTIES:
            for code in codes:
                assert code == code.upper(), (
                    f"Department code {code} should be uppercase"
                )


class TestGetActiveFaculties:
    def test_no_filter_returns_all(self):
        result = get_active_faculties(None)
        assert result == ALL_FACULTIES

    def test_filter_by_slug(self):
        result = get_active_faculties(["science"])
        assert len(result) == 1
        assert result[0][1] == "science"

    def test_filter_by_name(self):
        result = get_active_faculties(["Science"])
        assert len(result) == 1
        assert result[0][1] == "science"

    def test_filter_case_insensitive(self):
        result = get_active_faculties(["SCIENCE"])
        assert len(result) == 1

    def test_substring_fallback(self):
        result = get_active_faculties(["engineering"])
        assert len(result) >= 1
        assert any("engineering" in slug for _, slug, _ in result)

    def test_no_match_returns_empty(self):
        result = get_active_faculties(["nonexistent_faculty_xyz"])
        assert result == []


class TestProgramPages:
    def test_has_entries_for_key_faculties(self):
        for slug in ["agri-env-sci", "science", "engineering", "arts"]:
            assert slug in PROGRAM_PAGES, f"Missing program pages for {slug}"
            assert len(PROGRAM_PAGES[slug]) >= 2

    def test_paths_start_with_slash(self):
        for slug, paths in PROGRAM_PAGES.items():
            for path in paths:
                assert path.startswith("/"), (
                    f"Path {path} in {slug} should start with /"
                )

    def test_foundation_pages_seeded(self):
        agri_paths = PROGRAM_PAGES.get("agri-env-sci", [])
        assert any("foundation" in p for p in agri_paths), (
            "agri-env-sci should have a foundation program page"
        )

        sci_paths = PROGRAM_PAGES.get("science", [])
        assert any("foundation" in p for p in sci_paths), (
            "science should have a foundation program page"
        )


class TestDepartmentWebsites:
    def test_has_key_departments(self):
        for code in ["COMP", "MATH", "PHYS", "BIOL", "CHEM", "FDSC", "ECSE"]:
            assert code in DEPARTMENT_WEBSITES, f"Missing website for {code}"

    def test_urls_are_https(self):
        for code, url in DEPARTMENT_WEBSITES.items():
            assert url.startswith("https://"), (
                f"Website for {code} should be HTTPS: {url}"
            )

    def test_urls_end_with_slash(self):
        for code, url in DEPARTMENT_WEBSITES.items():
            assert url.endswith("/"), f"Website for {code} should end with /: {url}"


class TestDepartmentResources:
    def test_fdsc_has_student_society(self):
        assert "FDSC" in DEPARTMENT_RESOURCES
        res = DEPARTMENT_RESOURCES["FDSC"]
        assert "student_society" in res
        assert "student_society_url" in res

    def test_fdsc_has_foundation_email(self):
        res = DEPARTMENT_RESOURCES["FDSC"]
        assert "foundation_email" in res
        assert "macdonald" in res["foundation_email"]

    def test_fdsc_has_library_guide(self):
        res = DEPARTMENT_RESOURCES["FDSC"]
        assert "library_guide" in res
        assert "libraryguides" in res["library_guide"]

    def test_macdonald_depts_share_foundation_email(self):
        mac_depts = ["FDSC", "ANSC", "PLNT", "NRSC"]
        for code in mac_depts:
            assert code in DEPARTMENT_RESOURCES, f"Missing resources for {code}"
            assert "foundation_email" in DEPARTMENT_RESOURCES[code]


class TestFacultyResources:
    def test_agri_env_sci_has_foundation_page(self):
        assert "agri-env-sci" in FACULTY_RESOURCES
        assert "foundation_page" in FACULTY_RESOURCES["agri-env-sci"]

    def test_science_has_foundation_page(self):
        assert "science" in FACULTY_RESOURCES
        assert "foundation_page" in FACULTY_RESOURCES["science"]

    def test_foundation_urls_are_valid(self):
        for slug, res in FACULTY_RESOURCES.items():
            if "foundation_page" in res:
                url = res["foundation_page"]
                assert "coursecatalogue.mcgill.ca" in url or "mcgill.ca" in url


class TestCurriculumInterestMapping:
    def test_exact_match(self):
        assembler = CurriculumAssembler()
        domains = assembler.map_interests_to_domains(["computer science"])
        assert "COMP" in domains

    def test_multiple_interests(self):
        assembler = CurriculumAssembler()
        domains = assembler.map_interests_to_domains(["physics", "mathematics"])
        assert "PHYS" in domains
        assert "MATH" in domains

    def test_substring_match(self):
        assembler = CurriculumAssembler()
        domains = assembler.map_interests_to_domains(["machine"])
        # "machine" is substring of "machine learning"
        assert "COMP" in domains

    def test_direct_dept_code(self):
        assembler = CurriculumAssembler()
        domains = assembler.map_interests_to_domains(["FDSC"])
        assert "FDSC" in domains

    def test_unknown_interest_returns_empty(self):
        assembler = CurriculumAssembler()
        domains = assembler.map_interests_to_domains(["underwater basket weaving"])
        assert domains == []

    def test_case_insensitive(self):
        assembler = CurriculumAssembler()
        domains = assembler.map_interests_to_domains(["Computer Science"])
        assert "COMP" in domains

    def test_empty_input(self):
        assembler = CurriculumAssembler()
        assert assembler.map_interests_to_domains([]) == []
