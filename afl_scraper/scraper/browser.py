from contextlib import asynccontextmanager, contextmanager
from playwright.async_api import async_playwright
from playwright.sync_api import sync_playwright


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
