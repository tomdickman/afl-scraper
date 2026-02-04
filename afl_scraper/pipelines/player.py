from ..scraper import scrape_players, sync_browser_context, RawPlayer


def players_pipeline(year: int, headless: bool = True):
    with sync_browser_context(headless) as browser:
        raw_data = scrape_players(browser, year)
        print(raw_data)
