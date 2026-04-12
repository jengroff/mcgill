from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Callable

from backend.services.scraping.browser import browser_context

logger = logging.getLogger(__name__)

URL = "https://www.mcgill.ca/importantdates/"

START_DATE_FIELD = 'input[name="field_channels_event_date_value_1"]'
END_DATE_FIELD = 'input[name="field_channels_event_date_value2_1"]'

DATE_RANGE_START = "05/01/2026"
DATE_RANGE_END = "01/31/2028"

ProgressCallback = Callable[[str, str, int, int], None] | None


def _parse_date(text: str) -> date | None:
    """Parse a date string like 'Monday, September 7, 2026' into a date object."""
    text = text.strip().rstrip(".")
    for fmt in ("%A, %B %d, %Y", "%B %d, %Y", "%A %B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
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

        # The date text is in the preceding sibling or parent's preceding text.
        # Walk backwards from h3 to find the date string.
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

        # Also check the parent element's text before the h3
        if not date_text and h3.parent:
            parent_text = h3.parent.get_text(separator="\n", strip=True)
            lines = parent_text.split("\n")
            for line in lines:
                if re.search(r"\d{4}", line) and line != title:
                    date_text = line
                    break

        if not date_text:
            logger.debug("No date text found for entry: %s", title)
            continue

        # Parse date range — the page uses "to" as separator (no spaces around it sometimes)
        start_date = None
        end_date = None
        if "to" in date_text:
            parts = re.split(r"\bto\b", date_text, maxsplit=1)
            start_date = _parse_date(parts[0])
            end_date = _parse_date(parts[1])
        else:
            start_date = _parse_date(date_text)
            end_date = start_date

        if not start_date:
            logger.debug("Could not parse dates from: %r for %s", date_text, title)
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
    """Scrape McGill important dates page with date range filters and pagination.

    Navigates to the importantdates page, fills in the date range
    (May 2026 – January 2028), submits the filter form, paginates through
    all result pages, and upserts each date entry into the `important_dates`
    table.

    Returns the number of date entries stored.
    """
    from backend.db.postgres import get_pool

    def _progress(msg: str, current: int = 0, total: int = 0):
        logger.info("[important_dates] %s", msg)
        if on_progress:
            on_progress("important_dates", msg, current, total)

    _progress("Scraping important dates...")

    all_entries: list[dict] = []

    async with browser_context() as ctx:
        page = await ctx.new_page()

        await page.goto(URL, timeout=60000, wait_until="networkidle")

        # The date inputs are rendered by Drupal's date_popup / jQuery datepicker
        # after JS executes. Try the direct selector first; if it's not in the DOM,
        # fall back to setting values via JavaScript.
        try:
            await page.wait_for_selector(START_DATE_FIELD, timeout=10000)
            await page.fill(START_DATE_FIELD, DATE_RANGE_START)
            await page.fill(END_DATE_FIELD, DATE_RANGE_END)
            await page.press(END_DATE_FIELD, "Enter")
        except Exception:
            logger.info("Date inputs not found by name, setting values via JS")
            await page.evaluate(
                """([start, end]) => {
                    // Find date inputs by partial name match
                    const inputs = document.querySelectorAll('input[type="text"]');
                    for (const inp of inputs) {
                        const name = inp.name || '';
                        if (name.includes('event_date_value') && !name.includes('value2')) {
                            inp.value = start;
                            inp.dispatchEvent(new Event('change', {bubbles: true}));
                        } else if (name.includes('event_date_value2')) {
                            inp.value = end;
                            inp.dispatchEvent(new Event('change', {bubbles: true}));
                        }
                    }
                    // Try submitting the exposed filter form
                    const form = document.querySelector('.views-exposed-form form')
                        || document.querySelector('form[id*="views-exposed-form"]')
                        || document.querySelector('.views-exposed-form');
                    if (form && form.submit) {
                        form.submit();
                    } else {
                        // Click the apply/submit button
                        const btn = document.querySelector(
                            '.views-exposed-form input[type="submit"], '
                            + '.views-exposed-form button[type="submit"], '
                            + 'input[value="Apply"], button:has-text("Apply")'
                        );
                        if (btn) btn.click();
                    }
                }""",
                [DATE_RANGE_START, DATE_RANGE_END],
            )

        await page.wait_for_load_state("networkidle")

        page_num = 1
        while True:
            html = await page.content()
            entries = _parse_entries(html)
            all_entries.extend(entries)
            _progress(
                f"Page {page_num}: found {len(entries)} entries ({len(all_entries)} total)"
            )

            # Look for a "next page" link in the pager
            next_link = page.locator(
                'a[rel="next"], li.pager-next a, .pager__item--next a'
            )
            if await next_link.count() == 0:
                break

            await next_link.first.click()
            await page.wait_for_load_state("networkidle")
            page_num += 1

    if not all_entries:
        _progress("No date entries found")
        return 0

    # Upsert into database
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
