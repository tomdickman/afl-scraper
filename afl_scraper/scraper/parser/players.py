import re
from pathlib import Path
from io import open

from playwright.sync_api import Page

from ..constants import STATS_CLASSNAMES
from ..models import RawPlayer

"""Functions for parsing data from player(s) pages"""


def extract_player_id(url: str) -> str | None:
    """
    Extracts the player ID segment from URL.
    Handles both underscores and hyphens in the player ID.
    """

    # Regex pattern:
    # - looks for a slash
    # - then a single letter directory (e.g., "J/")
    # - then captures a sequence with letters, underscores or hyphens,
    #   followed by an optional number of any length
    # - stops at ".html"
    pattern = r"/players/[A-Za-z]/([A-Za-z_-]+[0-9]*)\.html$"

    match = re.search(pattern, url)
    if match:
        return match.group(1)
    return None


def scrape_player(page: Page) -> RawPlayer:
    """
    Scrape player data

    :param page: An AFL Tables /afl/stats/players page
    :type page: Page

    :returns: Scraped player data
    """
    id = extract_player_id(page.url)
    if id == None:
        raise ValueError(f"Error extracting player ID from {page.url}")

    path = Path(f"afl_scraper/data/raw/player/{id}.html")
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        f.write(page.content())

    # Remove trailing digits and split by
    first_name, raw_last_name = re.sub(r"\d+$", "", id).split("_", 1)
    last_name = raw_last_name.replace("_", " ")
    html = page.content()

    match = re.search(r"(\d{1,2}-[A-Za-z]{3}-\d{4})", html)

    date_of_birth = match.group(1) if match else None
    if date_of_birth == None:
        raise ValueError(f"Error parsing DOB for {page.url}")

    return RawPlayer(
        id=id,
        first_name=first_name,
        last_name=last_name,
        date_of_birth=date_of_birth,
    )


def scrape_players_links(page: Page):
    links = page.locator(STATS_CLASSNAMES["PLAYER_LINKS"]).all()

    hrefs = [link.get_attribute("href") for link in links]

    return hrefs
