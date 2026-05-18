from .browser import sync_browser_context, async_browser_context, get_team_page
from .scrape import scrape_match_ids, scrape_match, scrape_players
from .scrape_player_ids import (
    scrape_player_ids,
    save_player_ids_to_json,
)
from .sources import PlayerSource, PlayerSourceFactory, AFLTablesSource, AFLOfficialSource
from .fixture import get_fixture_page, get_round_buttons
from .models import RawMatchData, RawMatchDetails

__all__ = [
    # Browser context managers
    "sync_browser_context",
    "async_browser_context",
    "get_team_page",
    # Scraping functions
    "scrape_match_ids",
    "scrape_match",
    "scrape_players",
    "scrape_player_ids",
    "save_player_ids_to_json",
    # Player sources
    "PlayerSource",
    "PlayerSourceFactory",
    "AFLTablesSource",
    "AFLOfficialSource",
    # Fixture functions
    "get_fixture_page",
    "get_round_buttons",
    # Models
    "RawMatchDetails",
    "RawMatchData",
]
