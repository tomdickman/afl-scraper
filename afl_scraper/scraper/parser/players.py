from playwright.sync_api import Page

from ..constants import STATS_CLASSNAMES


def scrape_players_links(page: Page):
    links = page.locator(STATS_CLASSNAMES["PLAYER_LINKS"]).all()

    hrefs = [link.get_attribute('href') for link in links]

    return hrefs
