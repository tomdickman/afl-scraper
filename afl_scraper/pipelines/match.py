from ..scraper import scrape_match, sync_browser_context
from ..storage import admin_connection_pool, save_model
from ..transform.match import transform_match


def _resolve_player_id_from_db(name: str, team: str) -> str | None:
    parts = name.replace(".", "").split()
    if len(parts) < 2:
        return None

    first = parts[0]
    last = " ".join(parts[1:])

    with admin_connection_pool() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM player
                WHERE LOWER(givenname) = LOWER(%(first)s)
                  AND LOWER(familyname) = LOWER(%(last)s)
                LIMIT 1
                """,
                {"first": first, "last": last},
            )
            row = cur.fetchone()

    if row:
        return row[0]

    return None


def load_match_data(raw_data: dict, match_id: int) -> dict:
    """Transform and load scraped match data into the database."""
    game, player_stats = transform_match(
        raw_data,
        match_id=match_id,
        source="afl_official",
        resolve_player_id=_resolve_player_id_from_db,
    )

    with admin_connection_pool() as conn:
        # A match and all of its player statistics form one atomic unit. Any
        # failed statistic rolls back the game and every preceding statistic.
        with conn.transaction():
            game_result = save_model(conn, game)
            print(
                f"Game {match_id} "
                f"{'inserted' if game_result.was_inserted else 'updated'} in DB"
            )

            for pgs in player_stats:
                stats_result = save_model(conn, pgs)
                print(
                    f"  PGS {pgs.player_id} game#{pgs.game_id} "
                    f"{'inserted' if stats_result.was_inserted else 'updated'} in DB"
                )

    return {"game": game, "player_stats": player_stats}


def match_pipeline(match_id: int, headless: bool = True) -> dict:
    with sync_browser_context(headless) as browser:
        raw_data = scrape_match(browser, match_id)

    return load_match_data(raw_data, match_id)
