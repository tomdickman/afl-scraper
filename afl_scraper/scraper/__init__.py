from .browser import sync_browser_context, async_browser_context, get_team_page
from .scrape import (
    discover_official_season,
    save_season_manifest,
    scrape_match_ids,
    scrape_match,
    scrape_players,
)
from .scrape_player_ids import (
    scrape_player_ids,
    save_player_id_snapshots,
    save_player_ids_to_json,
)
from .sources import (
    PlayerSource,
    PlayerSourceFactory,
    AFLTablesSource,
    AFLOfficialSource,
)
from .fixture import get_fixture_page, get_fixture_url, get_round_buttons
from .models import DiscoveredRound, RawMatchData, RawMatchDetails, SeasonManifest

__all__ = [
    # Browser context managers
    "sync_browser_context",
    "async_browser_context",
    "get_team_page",
    # Scraping functions
    "scrape_match_ids",
    "discover_official_season",
    "save_season_manifest",
    "scrape_match",
    "scrape_players",
    "scrape_player_ids",
    "save_player_id_snapshots",
    "save_player_ids_to_json",
    # Player sources
    "PlayerSource",
    "PlayerSourceFactory",
    "AFLTablesSource",
    "AFLOfficialSource",
    # Fixture functions
    "get_fixture_page",
    "get_fixture_url",
    "get_round_buttons",
    # Models
    "RawMatchDetails",
    "RawMatchData",
    "DiscoveredRound",
    "SeasonManifest",
]
