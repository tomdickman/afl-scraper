from playwright.sync_api import sync_playwright

def health_check():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://afltables.com")
        page.wait_for_selector("h1")

        data = page.inner_text("h1")
        browser.close()

        return data == 'AFL Tables'
