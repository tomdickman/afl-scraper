from ..scraper import scrape_match, sync_browser_context


def match_pipeline(id: int, headless: bool = True):
    with sync_browser_context(headless) as browser:
        raw_data = scrape_match(browser, id)
        print(raw_data)
