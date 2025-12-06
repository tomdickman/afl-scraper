from playwright.sync_api import sync_playwright
from ..parser import extract_match_details, extract_player_stats, extract_table_data

from .paths import PATHS
from .css_selectors import CLASSNAMES
from .fixture import navigate_to_round, get_fixture_page

import pandas as pd

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

def scrape_match(id: int, headless: bool) -> pd.DataFrame:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)

        page = browser.new_page()
        page.goto(PATHS['MATCH'] + '/' + id)

        match_info = extract_match_details(page)
        print(match_info)

        page = extract_player_stats(page)
        df = extract_table_data(page)

        browser.close()
        return df
