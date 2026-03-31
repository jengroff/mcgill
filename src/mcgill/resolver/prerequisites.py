"""Parse prerequisite/restriction text into structured course references."""

from __future__ import annotations

import re

from mcgill.models.graph import PrerequisiteRef

_CODE_RE = re.compile(r"\b([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)\b")
_COREQ_MARKER = re.compile(r"\bcorequisite", re.IGNORECASE)
_RESTRICT_MARKER = re.compile(r"\brestrict", re.IGNORECASE)


def parse_prerequisites(
    source_code: str,
    prerequisites_raw: str,
    restrictions_raw: str,
    known_codes: set[str],
) -> list[PrerequisiteRef]:
    """Extract structured prerequisite/corequisite/restriction references."""
    refs: list[PrerequisiteRef] = []
    seen: set[tuple[str, str]] = set()

    # Parse prerequisites_raw
    if prerequisites_raw:
        is_coreq = bool(_COREQ_MARKER.search(prerequisites_raw))
        for m in _CODE_RE.finditer(prerequisites_raw):
            code = f"{m.group(1)} {m.group(2)}"
            if code == source_code or code not in known_codes:
                continue
            rel = "COREQUISITE_OF" if is_coreq else "PREREQUISITE_OF"
            key = (code, rel)
            if key not in seen:
                seen.add(key)
                refs.append(PrerequisiteRef(
                    source_code=source_code,
                    target_code=code,
                    relationship=rel,
                    raw_text=prerequisites_raw[:200],
                ))

    # Parse restrictions_raw
    if restrictions_raw:
        for m in _CODE_RE.finditer(restrictions_raw):
            code = f"{m.group(1)} {m.group(2)}"
            if code == source_code or code not in known_codes:
                continue
            key = (code, "RESTRICTED_WITH")
            if key not in seen:
                seen.add(key)
                refs.append(PrerequisiteRef(
                    source_code=source_code,
                    target_code=code,
                    relationship="RESTRICTED_WITH",
                    raw_text=restrictions_raw[:200],
                ))

    return refs
