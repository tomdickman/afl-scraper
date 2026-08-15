from ..scraper import scrape_match, sync_browser_context
from ..scraper.models import RawMatchData, RawPlayerStat
from ..storage import (
    admin_connection_pool,
    allocate_game_id,
    load_player_source_id_map,
    save_game_source_identity,
    save_model,
)
from ..transform.match import parse_match_datetime, transform_match


def _load_player_id_map(conn, raw_match: RawMatchData, year: int) -> dict[str, str]:
    official_ids = sorted(
        {
            stat.afl_official_id
            for stat in raw_match.home_team_stats + raw_match.away_team_stats
        }
    )
    return load_player_source_id_map(conn, "afl_official", year, official_ids)


def load_match_data(raw_data: RawMatchData | dict, match_id: int) -> dict:
    """Transform and load scraped match data into the database."""
    raw_match = RawMatchData.model_validate(raw_data)
    match_year = parse_match_datetime(
        raw_match.details.date, raw_match.details.time
    ).year

    with admin_connection_pool() as conn:
        # A match and all of its player statistics form one atomic unit. Any
        # failed statistic rolls back the game and every preceding statistic.
        with conn.transaction():
            player_id_map = _load_player_id_map(conn, raw_match, match_year)
            game_id, is_new_identity = allocate_game_id(
                conn, "afl_official", str(match_id)
            )

            def resolve_player_id(
                stat: RawPlayerStat, _team: str, _year: int
            ) -> str | None:
                return player_id_map.get(stat.afl_official_id)

            game, player_stats = transform_match(
                raw_match,
                match_id=game_id,
                source="afl_official",
                resolve_player_id=resolve_player_id,
            )
            game_result = save_model(conn, game)
            if is_new_identity:
                save_game_source_identity(conn, "afl_official", str(match_id), game_id)
            print(
                f"Game {match_id} (internal {game_id}) "
                f"{'inserted' if game_result.was_inserted else 'updated'} in DB"
            )

            for pgs in player_stats:
                stats_result = save_model(conn, pgs)
                print(
                    f"  PGS {pgs.player_id} game_id={pgs.game_id} "
                    f"{'inserted' if stats_result.was_inserted else 'updated'} in DB"
                )

    return {"game": game, "player_stats": player_stats}


def match_pipeline(match_id: int, headless: bool = True) -> dict:
    with sync_browser_context(headless) as browser:
        raw_data = scrape_match(browser, match_id)

    return load_match_data(raw_data, match_id)
