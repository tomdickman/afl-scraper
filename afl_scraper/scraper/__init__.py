from .browser import sync_browser_context, async_browser_context, get_team_page
from .australian_football import (
    australian_football_manifest_path,
    australian_football_match_cache_path,
    australian_football_match_url,
    australian_football_season_url,
    cache_australian_football_season_matches,
    discover_australian_football_season,
    load_australian_football_manifest,
    load_australian_football_match,
    parse_australian_football_match,
    parse_australian_football_season,
    save_australian_football_manifest,
    save_australian_football_match,
    scrape_australian_football_match,
)
from .scrape import (
    discover_official_season,
    load_raw_match_data,
    load_season_manifest,
    raw_match_data_path,
    save_raw_match_data,
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
from .models import (
    AustralianFootballMatchData,
    AustralianFootballMatchDetails,
    AustralianFootballPlayerStat,
    AustralianFootballSeasonManifest,
    CachedRawMatch,
    CachedAustralianFootballMatch,
    DiscoveredRound,
    RawMatchData,
    RawMatchDetails,
    SeasonManifest,
)
from .season_identities import collect_match_identities, scrape_season_player_ids

__all__ = [
    # Browser context managers
    "sync_browser_context",
    "async_browser_context",
    "get_team_page",
    # Scraping functions
    "australian_football_manifest_path",
    "australian_football_match_cache_path",
    "australian_football_match_url",
    "australian_football_season_url",
    "cache_australian_football_season_matches",
    "discover_australian_football_season",
    "load_australian_football_manifest",
    "load_australian_football_match",
    "parse_australian_football_match",
    "parse_australian_football_season",
    "save_australian_football_manifest",
    "save_australian_football_match",
    "scrape_australian_football_match",
    "scrape_match_ids",
    "discover_official_season",
    "load_raw_match_data",
    "load_season_manifest",
    "raw_match_data_path",
    "save_raw_match_data",
    "save_season_manifest",
    "scrape_match",
    "scrape_players",
    "scrape_player_ids",
    "save_player_id_snapshots",
    "save_player_ids_to_json",
    "collect_match_identities",
    "scrape_season_player_ids",
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
    "AustralianFootballMatchData",
    "AustralianFootballMatchDetails",
    "AustralianFootballPlayerStat",
    "AustralianFootballSeasonManifest",
    "CachedAustralianFootballMatch",
    "RawMatchDetails",
    "RawMatchData",
    "CachedRawMatch",
    "DiscoveredRound",
    "SeasonManifest",
]
