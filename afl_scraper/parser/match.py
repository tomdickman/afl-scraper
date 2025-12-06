import pandas as pd
import re

from playwright.sync_api import Locator, Page
from typing import List

from ..models import RawMatchDetails

from .css_selectors import CLASSNAMES

'''
Functions for parsing data from an individual match page.
'''

def extract_match_details(page: Page) -> RawMatchDetails:
    teams_info = page.locator(CLASSNAMES['MATCH_TEAMS'])
    round_date_time_info = page.locator(CLASSNAMES['MATCH_DATE_TIME'])
    venue_info = page.locator(CLASSNAMES['MATCH_VENUE'])

    teams = teams_info.inner_text().split(' v ')
    round, date_info, time_info = round_date_time_info.inner_text().split(' • ')
    venue, _land = re.sub(r"\s+", "", venue_info.inner_text()).split('•')

    if len(teams) != 2:
        raise ValueError("Could not parse team names from page")

    return {
        'home_team': teams[0],
        'away_team': teams[1],
        'round': round,
        'date': date_info,
        'time': time_info,
        'venue': venue
    }


def extract_player_stats(page: Page) -> Page:
    '''
    Carry out interactions on the match page to display the
    player statistics table.

    Args:
        page(Page): the specific match page

    Returns:
        Page: the match page with the Player Stats table displayed
    '''
    player_stats_btn = page.get_by_role('tab', name='Player Stats')
    player_stats_btn.click()

    return page


def _extract_header_columns(table) -> List[str]:
    '''
    Extract column headers from the table.

    Args:
        table: Playwright locator for the table element

    Returns:
        List[str]: List of column header names
    '''
    header_cells = table.locator('thead th').all()
    return [header_cell.inner_text() for header_cell in header_cells]

def _transform_table_cell(cell: Locator) -> str:
    '''
    Transform table cell contents into a more friendly format for data handling.

    Args:
        cell(Locator): Playwright locator for the cell

    Returns:
        str: The transformed string of cell content
    '''
    return re.sub(
        r'\n',
        '',
        cell.inner_text().strip()
    )

def _extract_data_rows(table: Locator, column_count: int) -> List[List[str]]:
    '''
    Extract data rows from the table body.

    Args:
        table: Playwright locator for the table element
        column_count(int): Number of columns in the table

    Returns:
        List[List[str]]: List of data rows, each row is a list of cell values
    '''
    data_cells = table.locator('tbody th, tbody td').all()
    cell_values = [_transform_table_cell(data_cell) for data_cell in data_cells]

    # Chunk the flat list of cell values into rows based on column count
    data_rows = []
    for i in range(0, len(cell_values), column_count):
        data_rows.append(cell_values[i:i + column_count])

    return data_rows


def extract_table_data(page: Page) -> pd.DataFrame:
    '''
    Extract tabular data from the stats table on the page.

    Args:
        page(Page): The match page containing the stats table

    Returns:
        pd.DataFrame: DataFrame containing the extracted table data with
                      appropriate column headers

    Raises:
        ValueError: If the table is not found or has invalid structure
    '''
    table = page.locator('.stats-table__table')

    # Verify table exists
    if table.count() == 0:
        raise ValueError("Stats table not found on page")

    # Extract headers and data
    columns = _extract_header_columns(table)

    if not columns:
        raise ValueError("No column headers found in table")

    data_rows = _extract_data_rows(table, len(columns))

    # Create and return DataFrame
    df = pd.DataFrame(data_rows, columns=columns)
    return df
