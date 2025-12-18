from datetime import datetime
from playwright.sync_api import BrowserContext, Page, Locator
from typing import Dict
from urllib.parse import urlencode

from .constants import FIXTURE_CLASSNAMES, PATHS, SEASON_ID


def get_fixture_page(browser: BrowserContext, year: int | None = None) -> Page:
    """
    Fetches the Page instance of the root fixture page

    Args:
        browser (BrowserContext):  the playwright browser context
        year (int):         the four digit year to get fixture for, defaults to the
                            current year if none selected.

    Returns:
        Page: the playwright page instance of the fixture page
    """
    page = browser.new_page()

    params = {
        "Competition": 1,
        "Season": SEASON_ID[year if (year != None) else datetime.now().year],
    }

    page.goto(f"{PATHS['FIXTURE']}?{urlencode(params)}")

    return page


def get_round_buttons(page: Page) -> Dict[str, Locator]:
    """
    Fetches button Locators for navigating between rounds

    Args:
        page (Page): the current playwright page instance

    Returns:
        Dict: a dictionary of Locator instances for the links
        to each round, keyed by the string value of the round
        number. Example: `{ 'OR': Locator, '1': Locator, ... }`
    """

    page.wait_for_selector(FIXTURE_CLASSNAMES["ROUND_NAV"])

    round_nav = page.locator(FIXTURE_CLASSNAMES["ROUND_NAV"])

    round_buttons = round_nav.get_by_role("button").all()

    keyed_buttons = {}

    for btn in round_buttons:
        key = btn.inner_text()
        keyed_buttons[key] = btn

    return keyed_buttons


def navigate_to_round(page: Page, round_number: str) -> Page:
    """Navigate to a specific round by round number.

    Args:
        page (Page): The page to navigate
        round_number (str): The round number, OR for Opening Round, finals maintain
            their string acronym (QF, SF, PF, GF etc.)

    Returns:
        Page: _description_
    """
    round_buttons = get_round_buttons(page)

    round_buttons[round_number].click()

    # TODO: Replace with a reliable site state we can look for instead
    # of using a timeout.
    page.wait_for_timeout(200)

    return page
