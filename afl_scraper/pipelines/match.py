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


def match_pipeline(id: int, headless: bool = True) -> dict:
    with sync_browser_context(headless) as browser:
        raw_data = scrape_match(browser, id)

    game, player_stats = transform_match(
        raw_data,
        match_id=id,
        source="afl_official",
        resolve_player_id=_resolve_player_id_from_db,
    )

    with admin_connection_pool() as conn:
        was_inserted, game_record_id = save_model(conn, game)
        print(f"Game {id} {'inserted' if was_inserted else 'updated'} in DB, id: {game_record_id}")

        for pgs in player_stats:
            was_ins, pgs_id = save_model(conn, pgs)
            print(f"  PGS {pgs.player_id} game#{pgs.player_game_number} {'inserted' if was_ins else 'updated'} in DB, id: {pgs_id}")

    return {"game": game, "player_stats": player_stats}
