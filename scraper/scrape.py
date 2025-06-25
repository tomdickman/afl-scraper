
from playwright.sync_api import sync_playwright
from .paths import PATHS
from .fixture import navigate_to_round

def scrape() -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(PATHS['FIXTURE'])
        text = navigate_to_round(page, 0)
        browser.close()

        return text
