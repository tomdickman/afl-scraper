from datetime import datetime

from ..scraper import scrape_players, sync_browser_context
from ..storage import admin_connection_pool, save_model
from ..transformer import transform_player_data


def players_pipeline(extract: bool = False, year: int = 2025):
    """
    Carry or full transform and load of Player data, with optional fresh
    extraction of unstructured data from source.

    Parameters
    ----------
    extract: bool
        Whether to extract fresh data from source into data lake

    """
    if extract:
        with sync_browser_context(False) as browser:
            scrape_players(browser, year)
    players = transform_player_data()

    with admin_connection_pool() as conn:
        for player in players:
            was_inserted, record_id = save_model(conn, player)
            print(f"Player {player.id} updated in DB, id: {record_id}")

    return players
