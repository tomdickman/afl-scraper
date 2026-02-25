import re
from pathlib import Path
from io import open

from playwright.sync_api import Page

from ..constants import STATS_CLASSNAMES

"""Functions for parsing data from player(s) pages"""


def extract_player_id(url: str) -> str | None:
    """
    Extracts the player ID segment from URL.
    Handles both underscores and hyphens in the player ID.

    Parameters
    ----------
    url: str
        The player stats page URL

    Returns
    -------
    str
        The player ID

    Raises
    ------
    RuntimeError
        If the player ID cannot be parsed
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
    raise RuntimeError(f"Failed to parse player ID from URL: {url}")


def scrape_player(page: Page) -> Path:
    """
    Scrape unstructured player data into data lake

    Parameters
    ----------
    page: Page
        An AFL Tables /afl/stats/players page

    Returns
    -------
    Path
        The path to the scraped data
    """
    id = extract_player_id(page.url)
    if id == None:
        raise ValueError(f"Error extracting player ID from {page.url}")

    path = Path(f"afl_scraper/data/raw/player/{id}.html")
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        f.write(page.content())

    # Validate that the file was created.
    if not path.exists():
        raise FileNotFoundError(f"Failed to create file at {path}")

    if path.stat().st_size == 0:
        raise ValueError(f"File created at {path} is empty")

    return path

def scrape_players_links(page: Page) -> list[str]:
    """
    Scrape links to raw player data

    Parameters
    ----------
    page: Page
        An AFL Tables /afl/stats/{year} page

    Returns
    -------
    list[str]
        A list of links to player pages
    """
    links = page.locator(STATS_CLASSNAMES["PLAYER_LINKS"]).all()

    hrefs = [link.get_attribute("href") for link in links]

    return hrefs
