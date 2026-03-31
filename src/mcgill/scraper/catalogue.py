"""Main course catalogue scraper — orchestrates browser, parsing, and storage."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import AsyncGenerator, Callable

from mcgill.config import settings
from mcgill.models.course import CourseCreate
from mcgill.scraper.browser import browser_context, fetch_page
from mcgill.scraper.faculties import (
    ALL_FACULTIES,
    PROGRAM_PAGES,
    get_active_faculties,
)
from mcgill.scraper.parser import parse_course, extract_variants

BASE_URL = "https://coursecatalogue.mcgill.ca"
DATA_DIR = Path(__file__).resolve().parents[3] / "data"


# Type for progress callbacks (phase, message, current, total)
ProgressCallback = Callable[[str, str, int, int], None] | None


async def run(
    faculty_filter: list[str] | None = None,
    max_course_pages: int | None = None,
    max_program_pages: int | None = None,
    headless: bool | None = None,
    on_progress: ProgressCallback = None,
) -> list[CourseCreate]:
    active = get_active_faculties(faculty_filter)
    if not active:
        raise ValueError("No matching faculties found for the given filter")

    active_prefixes = {p for _, _, prefixes in active for p in prefixes}
    active_pages = [
        path for _, slug, _ in active for path in PROGRAM_PAGES.get(slug, [])
    ]

    dept_to_faculties: dict[str, list[str]] = {}
    for name, _, prefixes in active:
        for p in prefixes:
            dept_to_faculties.setdefault(p, []).append(name)

    def _progress(phase: str, msg: str, current: int = 0, total: int = 0):
        print(f"[{phase}] {msg}")
        if on_progress:
            on_progress(phase, msg, current, total)

    _progress("scrape", f"Starting scrape for {len(active)} faculties, {len(active_prefixes)} dept prefixes")

    if headless is None:
        headless = settings.scraper_headless

    async with browser_context(headless=headless) as ctx:
        page = await ctx.new_page()

        # Phase 1a: Fetch catalog index
        _progress("scrape", "Fetching catalog index...")
        html = await fetch_page(page, f"{BASE_URL}/courses/")
        if not html:
            raise RuntimeError("Could not fetch catalog index")

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        slugs = list(dict.fromkeys(
            m.group(1)
            for a in soup.find_all("a", href=True)
            if (m := re.match(r"^/courses/([a-z]+-\d+[a-z]?)/index\.html$", a["href"]))
            and m.group(1).split("-")[0].upper() in active_prefixes
        ))
        if max_course_pages is not None:
            slugs = slugs[:max_course_pages]

        _progress("scrape", f"Found {len(slugs)} course pages to scrape", 0, len(slugs))

        # Phase 1b: Scrape individual course pages
        records: dict[str, CourseCreate] = {}
        for i, slug in enumerate(slugs):
            dept = slug.split("-")[0].upper()
            facs = dept_to_faculties.get(dept, ["Unknown"])
            html = await fetch_page(page, f"{BASE_URL}/courses/{slug}/index.html")
            if html:
                rec = parse_course(slug, html, facs)
                if rec:
                    records[slug] = rec

            if (i + 1) % 50 == 0 or i == len(slugs) - 1:
                _progress("scrape", f"Scraped {i+1}/{len(slugs)} pages, {len(records)} parsed", i + 1, len(slugs))

            await asyncio.sleep(settings.scraper_delay_sec)

        _progress("scrape", f"Course scrape done: {len(records)} records")

        # Phase 1c: Extract name variants from program pages
        known = {r.code for r in records.values()}
        all_variants: dict[str, list[str]] = {}
        if max_program_pages is not None:
            active_pages = active_pages[:max_program_pages]

        _progress("variants", f"Scraping {len(active_pages)} program guide pages...", 0, len(active_pages))
        for i, path in enumerate(active_pages):
            html = await fetch_page(page, f"{BASE_URL}{path}")
            if html:
                pv = extract_variants(html, known)
                for code, ctxs in pv.items():
                    all_variants.setdefault(code, []).extend(ctxs)

            if (i + 1) % 10 == 0 or i == len(active_pages) - 1:
                _progress("variants", f"Processed {i+1}/{len(active_pages)} program pages", i + 1, len(active_pages))

            await asyncio.sleep(settings.scraper_delay_sec)

        # Deduplicate variants and attach to records
        all_variants = {k: list(dict.fromkeys(v)) for k, v in all_variants.items()}
        courses = list(records.values())
        for rec in courses:
            rec.name_variants = all_variants.get(rec.code, [])

        # Save to JSON
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DATA_DIR / "courses.json"
        with open(out_path, "w") as f:
            json.dump([c.model_dump() for c in courses], f, indent=2)
        _progress("scrape", f"Wrote {out_path} ({len(courses)} records)")

        return courses
