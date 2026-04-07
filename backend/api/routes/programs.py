"""Available programs endpoint for the plan creation picker."""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter

from backend.services.scraping.faculties import ALL_FACULTIES, PROGRAM_PAGES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/programs", tags=["Programs"])


@router.get("")
async def list_programs() -> list[dict]:
    """Return programs grouped by faculty, derived from PROGRAM_PAGES registry
    and enriched with titles from the program_pages table.
    """
    from backend.db.postgres import get_pool

    faculty_names = {slug: name for name, slug, _ in ALL_FACULTIES}

    # Fetch titles from DB for all known paths
    all_paths = [p for paths in PROGRAM_PAGES.values() for p in paths]
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT path, title FROM program_pages WHERE path = ANY($1)",
            all_paths,
        )
    title_map = {r["path"]: r["title"] for r in rows}

    grouped: dict[str, list[dict]] = {}
    for faculty_slug, paths in PROGRAM_PAGES.items():
        programs = []
        for path in paths:
            # Filter to actual program pages, not overview/index pages
            if not _is_program_path(path):
                continue

            slug = _slug_from_path(path)
            title = title_map.get(path) or _title_from_slug(slug)
            programs.append(
                {
                    "slug": slug,
                    "title": title,
                    "path": path,
                    "faculty_slug": faculty_slug,
                }
            )

        if programs:
            grouped[faculty_slug] = programs

    return [
        {
            "faculty_slug": fslug,
            "faculty_name": faculty_names.get(fslug, fslug),
            "programs": progs,
        }
        for fslug, progs in sorted(grouped.items())
    ]


def _is_program_path(path: str) -> bool:
    """True for paths that represent actual programs (not bare faculty/index pages)."""
    segments = [s for s in path.strip("/").split("/") if s]
    # Must have at least 4 segments: en / undergraduate / faculty / something
    if len(segments) < 4:
        return False
    # Exclude bare /programs/ index pages
    if segments[-1] == "programs":
        return False
    return True


def _slug_from_path(path: str) -> str:
    """Extract the last meaningful path segment as the program slug."""
    segments = [s for s in path.strip("/").split("/") if s]
    return segments[-1] if segments else path


def _title_from_slug(slug: str) -> str:
    """Convert a URL slug to a readable title as fallback."""
    return re.sub(r"[-_]+", " ", slug).strip().title()
