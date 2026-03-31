"""Course name normalization utilities."""

from __future__ import annotations

import re

_STRIP_RE = re.compile(r"[^a-z0-9\s]")
_MULTI_SPACE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    name = name.lower().strip()
    name = _STRIP_RE.sub("", name)
    name = _MULTI_SPACE.sub(" ", name)
    return name.strip()


def normalize_code(code: str) -> str:
    """Normalize a course code like 'comp250' or 'COMP 250' → 'COMP 250'."""
    code = code.strip().upper()
    m = re.match(r"([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)", code)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return code
