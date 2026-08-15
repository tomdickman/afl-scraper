from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from playwright.async_api import async_playwright
from playwright.sync_api import sync_playwright, BrowserContext, Page


@asynccontextmanager
async def async_browser_context(headless: bool = True):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        try:
            yield context
        finally:
            context.close()
            browser.close()


@contextmanager
def sync_browser_context(headless: bool = True):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        try:
            yield context
        finally:
            context.close()
            browser.close()


def get_team_page(browser: BrowserContext, team_slug: str) -> Page:
    """
    Fetches the Page instance of a team page on AFL official site.

    Args:
        browser: the playwright browser context
        team_slug: the URL-friendly team slug (e.g., "adelaide-crows", "brisbane")

    Returns:
        Page: the playwright page instance of the team page
    """
    page = browser.new_page()
    try:
        expected_url = f"https://www.afl.com.au/teams/{team_slug}"
        response = page.goto(expected_url)
        if response is None or not response.ok:
            status = response.status if response is not None else "no response"
            raise RuntimeError(f"AFL team page {team_slug!r} returned HTTP {status}")
        if page.url.rstrip("/") != expected_url:
            raise RuntimeError(
                f"AFL team page {team_slug!r} navigated to unexpected URL {page.url!r}"
            )
        return page
    except Exception:
        page.close()
        raise
