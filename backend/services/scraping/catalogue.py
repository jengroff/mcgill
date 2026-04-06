"""Main course catalogue scraper — orchestrates browser, parsing, and storage."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Callable

from backend.config import settings
from backend.models.course import CourseCreate
from backend.services.scraping.browser import browser_context, fetch_page
from backend.services.scraping.faculties import (
    ALL_FACULTIES,
    PROGRAM_PAGES,
    get_active_faculties,
)
from backend.services.scraping.parser import (
    parse_course,
    parse_program_page,
    extract_variants,
    discover_sub_pages,
)

BASE_URL = "https://coursecatalogue.mcgill.ca"
DATA_DIR = Path(__file__).resolve().parents[3] / "data"


# Type for progress callbacks (phase, message, current, total)
ProgressCallback = Callable[[str, str, int, int], None] | None


async def run(
    faculty_filter: list[str] | None = None,
    dept_filter: list[str] | None = None,
    max_course_pages: int | None = None,
    max_program_pages: int | None = None,
    headless: bool | None = None,
    on_progress: ProgressCallback = None,
) -> list[CourseCreate]:
    if dept_filter:
        # Find faculties containing the requested departments
        dept_set = {d.upper() for d in dept_filter}
        active = [
            (name, slug, prefixes)
            for name, slug, prefixes in ALL_FACULTIES
            if any(p in dept_set for p in prefixes)
        ]
        if not active:
            raise ValueError(
                f"No faculties found containing departments: {dept_filter}"
            )
        active_prefixes = dept_set
    else:
        active = get_active_faculties(faculty_filter)
        if not active:
            raise ValueError("No matching faculties found for the given filter")
        active_prefixes = {p for _, _, prefixes in active for p in prefixes}
    active_pages: list[tuple[str, str]] = []  # (faculty_slug, path)
    for _, slug, _ in active:
        for path in PROGRAM_PAGES.get(slug, []):
            active_pages.append((slug, path))

    dept_to_faculties: dict[str, list[str]] = {}
    for name, _, prefixes in active:
        for p in prefixes:
            dept_to_faculties.setdefault(p, []).append(name)

    def _progress(phase: str, msg: str, current: int = 0, total: int = 0):
        print(f"[{phase}] {msg}")
        if on_progress:
            on_progress(phase, msg, current, total)

    _progress(
        "scrape",
        f"Starting scrape for {len(active)} faculties, {len(active_prefixes)} dept prefixes",
    )

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
        slugs = list(
            dict.fromkeys(
                m.group(1)
                for a in soup.find_all("a", href=True)
                if (
                    m := re.match(
                        r"^/courses/([a-z]+-\d+[a-z]?)/index\.html$",
                        a["href"],  # type: ignore[arg-type]
                    )
                )
                and m.group(1).split("-")[0].upper() in active_prefixes
            )
        )
        if max_course_pages is not None:
            slugs = slugs[:max_course_pages]

        _progress("scrape", f"Found {len(slugs)} course pages to scrape", 0, len(slugs))

        # Phase 1b: Scrape individual course pages — upsert to DB immediately
        from backend.db.postgres import get_pool

        pool = await get_pool()

        records: dict[str, CourseCreate] = {}
        for i, slug in enumerate(slugs):
            dept = slug.split("-")[0].upper()
            facs = dept_to_faculties.get(dept, ["Unknown"])
            html = await fetch_page(page, f"{BASE_URL}/courses/{slug}/index.html")
            if html:
                rec = parse_course(slug, html, facs)
                if rec:
                    records[slug] = rec
                    async with pool.acquire() as conn:
                        await conn.execute(
                            """INSERT INTO courses (code, slug, title, dept, number, credits,
                                   faculty, terms, description, prerequisites_raw,
                                   restrictions_raw, notes_raw, url, name_variants)
                               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                               ON CONFLICT (code) DO UPDATE SET
                                   title = EXCLUDED.title,
                                   description = EXCLUDED.description,
                                   prerequisites_raw = EXCLUDED.prerequisites_raw,
                                   restrictions_raw = EXCLUDED.restrictions_raw,
                                   terms = EXCLUDED.terms,
                                   updated_at = now()""",
                            rec.code,
                            rec.slug,
                            rec.title,
                            rec.dept,
                            rec.number,
                            rec.credits,
                            rec.faculty,
                            rec.terms,
                            rec.description,
                            rec.prerequisites_raw,
                            rec.restrictions_raw,
                            rec.notes_raw,
                            rec.url,
                            rec.name_variants,
                        )

            if (i + 1) % 50 == 0 or i == len(slugs) - 1:
                _progress(
                    "scrape",
                    f"Scraped {i + 1}/{len(slugs)} pages, {len(records)} parsed",
                    i + 1,
                    len(slugs),
                )

            await asyncio.sleep(settings.scraper_delay_sec)

        _progress(
            "scrape", f"Course scrape done: {len(records)} records saved to database"
        )

        # Phase 1c: Extract name variants from program pages
        known = {r.code for r in records.values()}
        all_variants: dict[str, list[str]] = {}
        if max_program_pages is not None:
            active_pages = active_pages[:max_program_pages]

        seen_paths: set[str] = {path for _, path in active_pages}

        _progress(
            "programs",
            f"Scraping {len(active_pages)} program guide pages...",
            0,
            len(active_pages),
        )
        i = 0
        while i < len(active_pages):
            fac_slug, path = active_pages[i]
            html = await fetch_page(page, f"{BASE_URL}{path}")
            if html:
                pv = extract_variants(html, known)
                for code, ctxs in pv.items():
                    all_variants.setdefault(code, []).extend(ctxs)

                # Save program page content to DB
                pg_title, pg_content = parse_program_page(html)
                if pg_content:
                    async with pool.acquire() as conn:
                        await conn.execute(
                            """INSERT INTO program_pages (faculty_slug, path, title, content)
                               VALUES ($1, $2, $3, $4)
                               ON CONFLICT (path) DO UPDATE SET
                                   title = EXCLUDED.title,
                                   content = EXCLUDED.content,
                                   scraped_at = now()""",
                            fac_slug,
                            path,
                            pg_title,
                            pg_content,
                        )

                # Discover and enqueue sub-program pages
                for sub_path in discover_sub_pages(html, path):
                    if sub_path not in seen_paths:
                        seen_paths.add(sub_path)
                        active_pages.append((fac_slug, sub_path))

            if (i + 1) % 10 == 0 or i == len(active_pages) - 1:
                _progress(
                    "programs",
                    f"Processed {i + 1}/{len(active_pages)} program pages",
                    i + 1,
                    len(active_pages),
                )

            i += 1
            await asyncio.sleep(settings.scraper_delay_sec)

        # Deduplicate variants, attach to records, and update DB
        all_variants = {k: list(dict.fromkeys(v)) for k, v in all_variants.items()}
        courses = list(records.values())
        async with pool.acquire() as conn:
            for rec in courses:
                rec.name_variants = all_variants.get(rec.code, [])
                if rec.name_variants:
                    await conn.execute(
                        "UPDATE courses SET name_variants = $1 WHERE code = $2",
                        rec.name_variants,
                        rec.code,
                    )
        _progress(
            "variants",
            f"Updated name variants for {sum(1 for c in courses if c.name_variants)} courses",
        )

        # Save JSON snapshot
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DATA_DIR / "courses.json"
        with open(out_path, "w") as f:
            json.dump([c.model_dump() for c in courses], f, indent=2)
        _progress("scrape", f"Wrote {out_path} ({len(courses)} records)")

        return courses
