from backend.services.resolution.prerequisites import parse_prerequisites


KNOWN = {"COMP 202", "COMP 250", "COMP 206", "MATH 240", "MATH 141", "COMP 302"}


class TestParsePrerequisites:
    def test_extracts_prerequisite_codes(self):
        refs = parse_prerequisites(
            "COMP 250",
            "Prerequisite: COMP 202 and MATH 240",
            "",
            KNOWN,
        )
        codes = {r.target_code for r in refs}
        assert "COMP 202" in codes
        assert "MATH 240" in codes

    def test_all_marked_prerequisite_of(self):
        refs = parse_prerequisites(
            "COMP 250",
            "Prerequisite: COMP 202",
            "",
            KNOWN,
        )
        assert len(refs) == 1
        assert refs[0].relationship == "PREREQUISITE_OF"
        assert refs[0].source_code == "COMP 250"
        assert refs[0].target_code == "COMP 202"

    def test_corequisite_detection(self):
        refs = parse_prerequisites(
            "COMP 250",
            "Corequisite: MATH 240",
            "",
            KNOWN,
        )
        assert len(refs) == 1
        assert refs[0].relationship == "COREQUISITE_OF"

    def test_corequisite_keyword_anywhere(self):
        refs = parse_prerequisites(
            "COMP 250",
            "Prerequisite or Corequisite: MATH 141",
            "",
            KNOWN,
        )
        assert len(refs) == 1
        assert refs[0].relationship == "COREQUISITE_OF"

    def test_restriction_codes(self):
        refs = parse_prerequisites(
            "COMP 250",
            "",
            "Restriction: Not open to students who have taken COMP 206",
            KNOWN,
        )
        assert len(refs) == 1
        assert refs[0].relationship == "RESTRICTED_WITH"
        assert refs[0].target_code == "COMP 206"

    def test_filters_self_references(self):
        refs = parse_prerequisites(
            "COMP 250",
            "Prerequisite: COMP 250 and COMP 202",
            "",
            KNOWN,
        )
        codes = {r.target_code for r in refs}
        assert "COMP 250" not in codes
        assert "COMP 202" in codes

    def test_filters_unknown_codes(self):
        refs = parse_prerequisites(
            "COMP 250",
            "Prerequisite: FAKE 999 and COMP 202",
            "",
            KNOWN,
        )
        assert len(refs) == 1
        assert refs[0].target_code == "COMP 202"

    def test_deduplicates(self):
        refs = parse_prerequisites(
            "COMP 250",
            "Prerequisite: COMP 202 or COMP 202",
            "",
            KNOWN,
        )
        assert len(refs) == 1

    def test_both_prereq_and_restriction(self):
        refs = parse_prerequisites(
            "COMP 250",
            "Prerequisite: COMP 202",
            "Restriction: Not open to students who have taken COMP 206",
            KNOWN,
        )
        assert len(refs) == 2
        rels = {r.relationship for r in refs}
        assert "PREREQUISITE_OF" in rels
        assert "RESTRICTED_WITH" in rels

    def test_empty_inputs(self):
        refs = parse_prerequisites("COMP 250", "", "", KNOWN)
        assert refs == []

    def test_raw_text_truncated(self):
        long_text = "Prerequisite: COMP 202. " + "x" * 300
        refs = parse_prerequisites("COMP 250", long_text, "", KNOWN)
        assert len(refs[0].raw_text) <= 200

    def test_no_known_codes_returns_empty(self):
        refs = parse_prerequisites(
            "COMP 250",
            "Prerequisite: COMP 202",
            "",
            set(),
        )
        assert refs == []

    def test_multiple_restrictions(self):
        refs = parse_prerequisites(
            "COMP 302",
            "",
            "Restriction: Not open to students who have taken COMP 202 or COMP 206",
            KNOWN,
        )
        assert len(refs) == 2
        codes = {r.target_code for r in refs}
        assert codes == {"COMP 202", "COMP 206"}
