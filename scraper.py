from playwright.sync_api import sync_playwright
from cssselectors import ROUND_NAV

def health_check():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://afltables.com")
        page.wait_for_selector("h1")

        data = page.inner_text("h1")
        browser.close()

        return data == 'AFL Tables'

def scrape_data():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.afl.com.au/fixture")
        page.wait_for_selector(ROUND_NAV)
        
        round_nav = page.locator(ROUND_NAV)

        round_buttons = round_nav.get_by_role("button")
        text = ",".join(round_buttons.all_inner_texts())
        browser.close()

        return text
