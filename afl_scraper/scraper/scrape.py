from playwright.sync_api import sync_playwright

from .constants import FIXTURE_CLASSNAMES, PATHS
from .fixture import navigate_to_round, get_fixture_page
from .parser import display_player_stats, extract_table_data


def scrape_match_ids(round_number: int, year: int = None, headless: bool = True):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = get_fixture_page(browser, year)
        page = navigate_to_round(page, round_number)
        matches_locator = page.locator(FIXTURE_CLASSNAMES["MATCHES"])

        match_ids: list[str] = []

        for match_locator in matches_locator.all():
            match_ids.append(match_locator.get_attribute("data-match-id"))

        browser.close()

        return match_ids


def scrape_match(id: int, headless: bool):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)

        page = browser.new_page()
        page.goto(PATHS["MATCH"] + "/" + id)

        page = display_player_stats(page)
        data = extract_table_data(page)

        browser.close()
        return data
