from playwright.sync_api import sync_playwright

from .paths import PATHS
from .css_selectors import CLASSNAMES
from .fixture import navigate_to_round, get_fixture_page, get_round_buttons

def scrape() -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(PATHS['FIXTURE'])
        text = navigate_to_round(page, 0)
        browser.close()

        return text

def scrape_matches(round_number: int, headless: bool):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = get_fixture_page(browser)
        page = navigate_to_round(page, round_number)
        matches_locator = page.locator(CLASSNAMES['FIXTURE_MATCHES'])

        match_ids = []

        for match_locator in matches_locator.all():
            id = match_locator.get_attribute('data-match-id')
            round_id = match_locator.get_attribute('data-round-id')
            match_ids.append({
                'id': id,
                'round_id': round_id
            })

        print(match_ids)

        browser.close()

def scrape_match(id: int, headless: bool):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)

        page = browser.new_page()
        page.goto(PATHS['MATCH'] + '/' + id)
        page.click('[data-tab="#player-stats"]')
        page.wait_for_timeout(200)

        match_info = page.locator(CLASSNAMES['MATCH_TEAMS'])

        print(match_info.inner_text())

        browser.close()
