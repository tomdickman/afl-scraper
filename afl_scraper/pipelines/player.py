from datetime import datetime

from ..scraper import scrape_players, sync_browser_context
from ..storage import admin_connection_pool, save_model
from ..transformer import transform_player_data


def players_pipeline(
    extract: bool = False, year: int = 2026, source: str = "afl_tables"
):
    """
    Carry out full transform and load of Player data, with optional fresh
    extraction of unstructured data from source.

    Parameters
    ----------
    extract: bool
        Whether to extract fresh data from source into data lake
    source: str
        Source name for raw data directory (default: "afl_tables")

    """
    if extract:
        with sync_browser_context(False) as browser:
            scrape_players(browser, year, source)
    players = transform_player_data(source)

    with admin_connection_pool() as conn:
        for player in players:
            result = save_model(conn, player)
            print(f"Player {player.id} updated in DB, identity: {result.identity}")

    return players
