from playwright.sync_api import Page, Locator
from typing import Dict
from .css_selectors import CLASSNAMES

def get_round_buttons(page: Page) -> Dict[str, Locator]:
    '''
    Fetches button Locators for navigating between rounds
    
    Args:
        page (Page): the current playwright page instance
        
    Returns:
        Dict: a dictionary of Locator instances for the links
        to each round, keyed by the string value of the round
        number. Example: { 'OR': Locator, '1': Locator, ... }
    '''
    
    page.wait_for_selector(CLASSNAMES['ROUND_NAV'])
    
    round_nav = page.locator(CLASSNAMES['ROUND_NAV'])

    round_buttons = round_nav.get_by_role("button")
    
    keyed_buttons = {}
    
    for btn in round_buttons.all():
        key = btn.inner_text()
        keyed_buttons[key] = btn
    
    return keyed_buttons


def navigate_to_round(page: Page, round_number: int):
    # Handle the Opening Round case, passing in round `0` maps to 'OR'
    round_no = str(round_number) if round_number != 0 else 'OR'

    round_buttons = get_round_buttons(page)

    round_buttons[round_no].click()
    page.wait_for_load_state('networkidle')

    return page.url
