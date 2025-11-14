from playwright.sync_api import sync_playwright

from scraper import get_fixture_page, get_round_buttons

def smoke_test_fixture(headless: bool = True) -> bool:
    '''
    Run a smoke test on the AFL fixture page to check if any breaking
    changes may have occurred which could cause issues for fixture scraping.
    '''

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = get_fixture_page(browser)
        buttons = get_round_buttons(page)

        if 'OR' not in buttons.keys():
            print('🚨   Fixture smoke test failed')
        else:
            print('✅   Fixture smoke test passed')

        browser.close()

def smoke_test(headless: bool):
    smoke_test_fixture(headless)
