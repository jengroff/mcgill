from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from playwright.async_api import Page

from backend.config import settings
from backend.models.course import CourseCreate
from backend.services.scraping.browser import browser_context, fetch_page
from backend.services.scraping.faculties import (
    ALL_FACULTIES,
    GENERAL_INFO_PAGES,
    PROGRAM_PAGES,
    get_active_faculties,
)
from backend.services.scraping.parser import (
    parse_course,
    parse_program_page,
    extract_variants,
    discover_sub_pages,
)

logger = logging.getLogger(__name__)

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
        logger.info("[%s] %s", phase, msg)
        if on_progress:
            on_progress(phase, msg, current, total)

    _progress(
        "scrape",
        f"Starting scrape for {len(active)} faculties, {len(active_prefixes)} dept prefixes",
    )

    if headless is None:
        headless = settings.scraper_headless

    concurrency = settings.scraper_concurrency

    async with browser_context(headless=headless) as ctx:
        # Create a pool of browser pages for concurrent fetching
        page_pool: asyncio.Queue[Page] = asyncio.Queue()
        for _ in range(concurrency):
            page_pool.put_nowait(await ctx.new_page())

        # Phase 1a: Fetch catalog index
        _progress("scrape", "Fetching catalog index...")
        idx_page = await page_pool.get()
        html = await fetch_page(idx_page, f"{BASE_URL}/courses/")
        await page_pool.put(idx_page)

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

        # Phase 1b: Scrape individual course pages concurrently
        from backend.db.postgres import get_pool

        pool = await get_pool()

        records: dict[str, CourseCreate] = {}
        course_completed = 0
        course_parsed = 0

        async def _scrape_course(slug: str) -> tuple[str, CourseCreate] | None:
            nonlocal course_completed, course_parsed
            dept = slug.split("-")[0].upper()
            facs = dept_to_faculties.get(dept, ["Unknown"])
            pg = await page_pool.get()
            try:
                html = await fetch_page(pg, f"{BASE_URL}/courses/{slug}/index.html")
                result = None
                if html:
                    rec = parse_course(slug, html, facs)
                    if rec:
                        course_parsed += 1
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
                        result = (slug, rec)
                await asyncio.sleep(settings.scraper_delay_sec)
                return result
            finally:
                await page_pool.put(pg)
                course_completed += 1
                if course_completed % 50 == 0 or course_completed == len(slugs):
                    _progress(
                        "scrape",
                        f"Scraped {course_completed}/{len(slugs)} pages, {course_parsed} parsed",
                        course_completed,
                        len(slugs),
                    )

        course_results = await asyncio.gather(*[_scrape_course(s) for s in slugs])
        for r in course_results:
            if r:
                records[r[0]] = r[1]

        _progress(
            "scrape", f"Course scrape done: {len(records)} records saved to database"
        )

        # Phase 1c: Extract name variants from program pages (concurrent workers)
        known = {r.code for r in records.values()}
        all_variants: dict[str, list[str]] = {}
        if max_program_pages is not None:
            active_pages = active_pages[:max_program_pages]

        seen_paths: set[str] = {path for _, path in active_pages}
        program_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        for item in active_pages:
            program_queue.put_nowait(item)

        program_total = len(active_pages)
        program_completed = 0
        workers_active = 0

        _progress(
            "programs",
            f"Scraping {program_total} program guide pages...",
            0,
            program_total,
        )

        async def _program_worker():
            nonlocal program_total, program_completed, workers_active
            pg = await page_pool.get()
            try:
                while True:
                    try:
                        fac_slug, path = program_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        if workers_active == 0:
                            break
                        await asyncio.sleep(0.1)
                        continue

                    workers_active += 1
                    try:
                        html = await fetch_page(pg, f"{BASE_URL}{path}")
                        if html:
                            pv = extract_variants(html, known)
                            for code, ctxs in pv.items():
                                all_variants.setdefault(code, []).extend(ctxs)

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

                            for sub_path in discover_sub_pages(html, path):
                                if sub_path not in seen_paths:
                                    seen_paths.add(sub_path)
                                    program_queue.put_nowait((fac_slug, sub_path))
                                    program_total += 1
                    finally:
                        workers_active -= 1

                    program_completed += 1
                    if program_completed % 10 == 0:
                        _progress(
                            "programs",
                            f"Processed {program_completed}/{program_total} program pages",
                            program_completed,
                            program_total,
                        )

                    await asyncio.sleep(settings.scraper_delay_sec)
            finally:
                await page_pool.put(pg)

        n_program_workers = min(concurrency, max(len(active_pages), 1))
        await asyncio.gather(*[_program_worker() for _ in range(n_program_workers)])

        _progress(
            "programs",
            f"Processed {program_completed}/{program_total} program pages",
            program_completed,
            program_total,
        )

        # Phase 1d: Scrape external advising pages concurrently
        from backend.services.scraping.faculties import EXTERNAL_ADVISING_PAGES

        ext_pages = []
        for fac_slug, urls in EXTERNAL_ADVISING_PAGES.items():
            if active and fac_slug not in {s for _, s, _ in active}:
                continue
            for url in urls:
                ext_pages.append((fac_slug, url))

        if ext_pages:
            adv_completed = 0

            _progress(
                "advising",
                f"Scraping {len(ext_pages)} external advising pages...",
                0,
                len(ext_pages),
            )

            async def _scrape_advising(fac_slug: str, url: str):
                nonlocal adv_completed
                pg = await page_pool.get()
                try:
                    html = await fetch_page(pg, url)
                    if html:
                        pg_title, pg_content = parse_program_page(html)
                        if pg_content:
                            url_path = urlparse(url).path
                            async with pool.acquire() as conn:
                                await conn.execute(
                                    """INSERT INTO program_pages (faculty_slug, path, title, content)
                                       VALUES ($1, $2, $3, $4)
                                       ON CONFLICT (path) DO UPDATE SET
                                           title = EXCLUDED.title,
                                           content = EXCLUDED.content,
                                           scraped_at = now()""",
                                    fac_slug,
                                    url_path,
                                    pg_title,
                                    pg_content,
                                )
                    await asyncio.sleep(settings.scraper_delay_sec)
                finally:
                    await page_pool.put(pg)
                    adv_completed += 1
                    if adv_completed % 5 == 0 or adv_completed == len(ext_pages):
                        _progress(
                            "advising",
                            f"Processed {adv_completed}/{len(ext_pages)} advising pages",
                            adv_completed,
                            len(ext_pages),
                        )

            await asyncio.gather(*[_scrape_advising(fs, u) for fs, u in ext_pages])

        # Phase 1e: Scrape general university info pages concurrently
        gen_pages = [
            (category, url)
            for category, urls in GENERAL_INFO_PAGES.items()
            for url in urls
        ]

        if gen_pages:
            gen_completed = 0

            _progress(
                "general",
                f"Scraping {len(gen_pages)} general info pages...",
                0,
                len(gen_pages),
            )

            async def _scrape_general(category: str, url: str):
                nonlocal gen_completed
                pg = await page_pool.get()
                try:
                    html = await fetch_page(pg, url)
                    if html:
                        pg_title, pg_content = parse_program_page(html)
                        if pg_content:
                            url_path = urlparse(url).path
                            async with pool.acquire() as conn:
                                await conn.execute(
                                    """INSERT INTO program_pages (faculty_slug, path, title, content)
                                       VALUES ($1, $2, $3, $4)
                                       ON CONFLICT (path) DO UPDATE SET
                                           title = EXCLUDED.title,
                                           content = EXCLUDED.content,
                                           scraped_at = now()""",
                                    "university",
                                    url_path,
                                    pg_title or category.replace("-", " ").title(),
                                    pg_content,
                                )
                    await asyncio.sleep(settings.scraper_delay_sec)
                finally:
                    await page_pool.put(pg)
                    gen_completed += 1
                    if gen_completed % 5 == 0 or gen_completed == len(gen_pages):
                        _progress(
                            "general",
                            f"Processed {gen_completed}/{len(gen_pages)} general info pages",
                            gen_completed,
                            len(gen_pages),
                        )

            await asyncio.gather(*[_scrape_general(c, u) for c, u in gen_pages])

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
