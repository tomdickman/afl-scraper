from typing import List
from playwright.sync_api import BrowserContext

from ..scraper import RawPlayer

from .constants import FIXTURE_CLASSNAMES, PATHS
from .fixture import navigate_to_round, get_fixture_page
from .parser import (
    display_player_stats,
    extract_table_data,
    scrape_player,
    scrape_players_links,
)


def scrape_match_ids(browser: BrowserContext, round_number: int, year: int = None):
    page = get_fixture_page(browser, year)
    page = navigate_to_round(page, round_number)
    matches_locator = page.locator(FIXTURE_CLASSNAMES["MATCHES"])

    match_ids: List[str] = []

    for match_locator in matches_locator.all():
        match_ids.append(match_locator.get_attribute("data-match-id"))

    return match_ids


def scrape_match(browser: BrowserContext, id: int):
    page = browser.new_page()
    page.goto(PATHS["MATCH"] + "/" + id)

    page = display_player_stats(page)
    data = extract_table_data(page)

    return data


def scrape_players(browser: BrowserContext, year: int) -> List[RawPlayer]:
    page = browser.new_page()
    page.goto(f"https://afltables.com/afl/stats/{year}.html")

    links = scrape_players_links(page)

    players = []

    for link in links:
        page.goto(f"https://afltables.com/afl/stats/{link}")
        player = scrape_player(page)
        if player != None:
            print(player)
            players.append(player)

    return players
