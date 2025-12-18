from playwright.sync_api import BrowserContext

from .browser import sync_browser_context
from .constants import FIXTURE_CLASSNAMES, PATHS
from .fixture import navigate_to_round, get_fixture_page
from .parser import display_player_stats, extract_table_data


def scrape_match_ids(browser: BrowserContext, round_number: int, year: int = None):
    page = get_fixture_page(browser, year)
    page = navigate_to_round(page, round_number)
    matches_locator = page.locator(FIXTURE_CLASSNAMES["MATCHES"])

    match_ids: list[str] = []

    for match_locator in matches_locator.all():
        match_ids.append(match_locator.get_attribute("data-match-id"))

    return match_ids


def scrape_match(browser: BrowserContext, id: int):
    page = browser.new_page()
    page.goto(PATHS["MATCH"] + "/" + id)

    page = display_player_stats(page)
    data = extract_table_data(page)

    return data
