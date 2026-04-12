from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Callable

from backend.services.scraping.browser import browser_context

logger = logging.getLogger(__name__)

URL = "https://www.mcgill.ca/importantdates/"
CUTOFF_DATE = date(2026, 5, 1)

ProgressCallback = Callable[[str, str, int, int], None] | None


def _normalize_date_text(text: str) -> str:
    """Re-insert spaces that BeautifulSoup's strip=True removes.

    Turns 'Tuesday,July1,2025toSunday,April19,2026'
    into  'Tuesday, July 1, 2025 to Sunday, April 19, 2026'.
    """
    text = re.sub(r",(?=\S)", ", ", text)
    text = re.sub(r"([a-zA-Z])(\d)", r"\1 \2", text)
    text = re.sub(r"(\d)([a-zA-Z])", r"\1 \2", text)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return text.strip()


def _parse_date(text: str) -> date | None:
    """Parse a date string like 'Monday, September 7, 2026' into a date object."""
    text = text.strip().rstrip(".")
    # Strip trailing time like '10:00', '23:59'
    text = re.sub(r"\s*\d{1,2}:\d{2}\s*$", "", text)
    for fmt in ("%A, %B %d, %Y", "%B %d, %Y", "%A %B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    if text:
        logger.warning("Could not parse date: %r", text)
    return None


def _parse_entries(html: str) -> list[dict]:
    """Extract date entries from the page HTML.

    Each entry on the importantdates page is rendered as a result block with:
    - A date or date range as text (e.g. "Friday, October 9, 2026toWednesday, October 14, 2026")
    - An h3 > a element containing the event title
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    entries: list[dict] = []

    for h3 in soup.find_all("h3"):
        link = h3.find("a", href=re.compile(r"/importantdates/"))
        if not link:
            continue

        title = link.get_text(strip=True)
        if not title:
            continue

        date_text = ""
        for sib in h3.previous_siblings:
            text = (
                sib.get_text(strip=True)
                if hasattr(sib, "get_text")
                else str(sib).strip()
            )
            if text and re.search(r"\d{4}", text):
                date_text = text
                break

        if not date_text and h3.parent:
            parent_text = h3.parent.get_text(separator="\n", strip=True)
            lines = parent_text.split("\n")
            for line in lines:
                if re.search(r"\d{4}", line) and line != title:
                    date_text = line
                    break

        if not date_text:
            continue

        date_text = _normalize_date_text(date_text)

        start_date = None
        end_date = None
        if " to " in date_text:
            parts = date_text.split(" to ", 1)
            start_date = _parse_date(parts[0])
            end_date = _parse_date(parts[1])
        else:
            start_date = _parse_date(date_text)
            end_date = start_date

        if not start_date:
            continue

        entries.append(
            {
                "title": title,
                "start_date": start_date,
                "end_date": end_date or start_date,
            }
        )

    return entries


async def scrape_important_dates(on_progress: ProgressCallback = None) -> int:
    """Scrape the full McGill important dates listing, keeping entries from May 2026 onward.

    Paginates through the default (unfiltered) view, parses each entry,
    filters by date, deduplicates, and upserts into the `important_dates` table.
    """
    from backend.db.postgres import get_pool

    def _progress(msg: str, current: int = 0, total: int = 0):
        logger.info("[important_dates] %s", msg)
        if on_progress:
            on_progress("important_dates", msg, current, total)

    _progress("Scraping important dates...")

    all_entries: list[dict] = []
    seen: set[tuple[str, str]] = set()

    async with browser_context() as ctx:
        page = await ctx.new_page()

        MAX_PAGES = 100
        consecutive_empty = 0

        for page_num in range(MAX_PAGES):
            url = f"{URL}?page={page_num}" if page_num > 0 else URL
            await page.goto(url, timeout=60000, wait_until="networkidle")

            html = await page.content()
            entries = _parse_entries(html)

            new_entries = []
            for e in entries:
                key = (e["title"], str(e["start_date"]))
                if key in seen:
                    continue
                seen.add(key)
                effective_end = e["end_date"] or e["start_date"]
                if effective_end >= CUTOFF_DATE:
                    new_entries.append(e)

            all_entries.extend(new_entries)
            _progress(
                f"Page {page_num + 1}: {len(entries)} parsed, {len(new_entries)} kept ({len(all_entries)} total)"
            )

            if not entries:
                break

            # Stop after 3 consecutive pages with no new qualifying entries
            if not new_entries:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break
            else:
                consecutive_empty = 0

    if not all_entries:
        _progress("No date entries found")
        return 0

    pool = await get_pool()
    stored = 0
    async with pool.acquire() as conn:
        for entry in all_entries:
            await conn.execute(
                """INSERT INTO important_dates (title, start_date, end_date)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (title, start_date) DO UPDATE SET
                       end_date = EXCLUDED.end_date,
                       scraped_at = now()""",
                entry["title"],
                entry["start_date"],
                entry["end_date"],
            )
            stored += 1

    _progress(f"Stored {stored} important dates")
    return stored
