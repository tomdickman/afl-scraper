from pathlib import Path
from typing import List

from playwright.sync_api import BrowserContext

from .constants import FIXTURE_CLASSNAMES, PATHS
from .fixture import navigate_to_round, get_fixture_page
from .parser import (
    display_player_stats,
    extract_table_data,
)
from .sources import PlayerSourceFactory


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

    # Open the team selector dropdown
    page.locator("button#teams-dropdown-button").click()
    # Select home team
    page.locator(".select__options-wrapper").locator("li:nth-child(2)").click()

    path = Path(f"afl_scraper/data/raw/match/{id}/home_player_stats.html")
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        f.write(page.content())

    # Validate that the file was created.
    if not path.exists():
        raise FileNotFoundError(f"Failed to create file at {path}")

    if path.stat().st_size == 0:
        raise ValueError(f"File created at {path} is empty")

    # Open the team selector dropdown
    page.locator("button#teams-dropdown-button").click()
    # Select away team
    page.locator(".select__options-wrapper").locator("li:nth-child(3)").click()

    path = Path(f"afl_scraper/data/raw/match/{id}/home_player_stats.html")
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        f.write(page.content())

    # Validate that the file was created.
    if not path.exists():
        raise FileNotFoundError(f"Failed to create file at {path}")

    if path.stat().st_size == 0:
        raise ValueError(f"File created at {path} is empty")

    data = extract_table_data(page)

    return data


def scrape_players(browser: BrowserContext, year: int, source: str = "afl_tables") -> List[Path]:
    source_obj = PlayerSourceFactory.get(source)
    page = browser.new_page()
    page.goto(source_obj.get_list_page_url(year))

    links = source_obj.scrape_players_links(page)

    players_data_paths = []

    for link in links:
        page.goto(f"https://afltables.com/afl/stats/{link}")
        player_data_path = source_obj.scrape_player(page)
        if player_data_path != None:
            print(f"Player path scraped: {player_data_path}")
            players_data_paths.append(player_data_path)

    return players_data_paths
