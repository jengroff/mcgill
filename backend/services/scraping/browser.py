from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from playwright.async_api import async_playwright, Page, BrowserContext

from backend.config import settings

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@asynccontextmanager
async def browser_context(
    headless: bool | None = None,
) -> AsyncGenerator[BrowserContext, None]:
    if headless is None:
        headless = settings.scraper_headless
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, args=["--no-sandbox"])
        ctx = await browser.new_context(
            user_agent=USER_AGENT,
            locale="en-US",
            viewport={"width": 1280, "height": 800},
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        try:
            yield ctx
        finally:
            await ctx.close()
            await browser.close()


async def fetch_page(page: Page, url: str) -> str | None:
    try:
        response = await page.goto(
            url,
            timeout=settings.scraper_timeout_ms,
            wait_until="domcontentloaded",
        )
        if response is None or response.status != 200:
            return None
        return await page.content()
    except Exception:
        return None
