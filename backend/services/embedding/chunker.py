from __future__ import annotations

import re

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")

WINDOW_SIZE = 3
OVERLAP = 1


def split_sentences(text: str) -> list[str]:
    if not text.strip():
        return []
    return [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]


def chunk_course(
    code: str,
    title: str,
    description: str,
    prerequisites_raw: str = "",
    restrictions_raw: str = "",
    notes_raw: str = "",
    dept: str = "",
    faculty: str = "",
    window_size: int = WINDOW_SIZE,
    overlap: int = OVERLAP,
) -> list[str]:
    """Create sentence-window chunks for a single course.

    Each chunk starts with faculty/department context for retrieval.
    """
    context_parts = [f"Course: {code} — {title}."]
    if faculty or dept:
        context_parts.append(f"Faculty: {faculty}, Department: {dept}.")
    prefix = " ".join(context_parts)

    # Combine all text fields
    parts = [description]
    if prerequisites_raw:
        parts.append(f"Prerequisites: {prerequisites_raw}")
    if restrictions_raw:
        parts.append(f"Restrictions: {restrictions_raw}")
    if notes_raw:
        parts.append(f"Notes: {notes_raw}")

    full_text = " ".join(p for p in parts if p)
    sentences = split_sentences(full_text)

    if not sentences:
        return [prefix]

    # If fewer sentences than window size, return single chunk
    if len(sentences) <= window_size:
        return [f"{prefix} {' '.join(sentences)}"]

    chunks = []
    step = max(1, window_size - overlap)
    for i in range(0, len(sentences), step):
        window = sentences[i : i + window_size]
        chunks.append(f"{prefix} {' '.join(window)}")
        if i + window_size >= len(sentences):
            break

    return chunks


_TABLE_ROW = re.compile(r"^\|.*\|$")


def _split_program_sections(content: str) -> list[str]:
    """Split program page content into sections, keeping markdown tables intact.

    Markdown tables (rows starting and ending with `|`) are grouped into a
    single section so course requirement tables don't get fragmented across
    chunks.
    """
    sections: list[str] = []
    table_lines: list[str] = []

    for line in content.split("\n"):
        stripped = line.strip()
        if _TABLE_ROW.match(stripped):
            table_lines.append(stripped)
        else:
            if table_lines:
                sections.append("\n".join(table_lines))
                table_lines = []
            if stripped:
                sentences = split_sentences(stripped)
                sections.extend(sentences if sentences else [stripped])

    if table_lines:
        sections.append("\n".join(table_lines))

    return sections


def chunk_program_page(
    title: str,
    content: str,
    faculty_slug: str,
    window_size: int = WINDOW_SIZE,
    overlap: int = OVERLAP,
) -> list[str]:
    """Create chunks for a program guide page.

    Markdown tables (course requirement lists) are kept intact as single
    chunks so downstream retrieval returns the complete course list rather
    than fragments.
    """
    prefix = f"Program: {title}. Faculty: {faculty_slug}."

    sections = _split_program_sections(content)

    if not sections:
        return [prefix] if title else []

    if len(sections) <= window_size:
        return [f"{prefix} {' '.join(sections)}"]

    chunks = []
    step = max(1, window_size - overlap)
    for i in range(0, len(sections), step):
        window = sections[i : i + window_size]
        chunk_text = " ".join(window)
        chunks.append(f"{prefix} {chunk_text}")
        if i + window_size >= len(sections):
            break

    return chunks
