from ..scraper import scrape_players, sync_browser_context
from ..storage import admin_connection_pool, save_model
from ..transform import transform_player_data


def players_pipeline(
    extract: bool = False,
    year: int = 2026,
    source: str = "afl_tables",
    progress=None,
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

    with admin_connection_pool() as conn, conn.transaction():
        # Treat a player sync as one explicit unit of work. Although the pool's
        # connection context also commits on successful exit, keeping the
        # transaction here makes the pipeline's atomicity independent of that
        # connection-management detail.
        for player in players:
            result = save_model(conn, player)
            if progress is not None:
                progress(player.id, result.was_inserted, result.identity)

    return players
