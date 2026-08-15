"""Transform validated AustralianFootball caches into canonical DB models."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..models import Game, PlayerGameStats
from ..scraper.models import AustralianFootballMatchData
from .match import resolve_team, resolve_venue


SOURCE = "australian_football"
_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "config"


def _load_jsonc(path: Path) -> dict:
    return json.loads(re.sub(r"//.*", "", path.read_text(encoding="utf-8")))


def historical_match_datetime(match: AustralianFootballMatchData, venue_id: str):
    mappings = _load_jsonc(_CONFIG_ROOT / "venue_timezones.jsonc")
    timezone_name = mappings.get(venue_id)
    if timezone_name is None:
        raise KeyError(f"No timezone mapping found for canonical venue {venue_id!r}")
    try:
        venue_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            f"Invalid IANA timezone {timezone_name!r} for venue {venue_id!r}"
        ) from exc

    naive = datetime.combine(match.details.date, match.details.local_time)
    aware = naive.replace(tzinfo=venue_timezone)
    round_trip = aware.astimezone(timezone.utc).astimezone(venue_timezone)
    if round_trip.replace(tzinfo=None) != naive:
        raise ValueError(
            f"Nonexistent local match time {naive.isoformat()} at {venue_id}"
        )
    return aware


def transform_australian_football_match(
    raw_data: AustralianFootballMatchData | dict,
    *,
    game_id: int,
    player_id_map: dict[str, str],
) -> tuple[Game, list[PlayerGameStats]]:
    """Transform without inventing statistics absent from the source."""
    match = AustralianFootballMatchData.model_validate(raw_data)
    details = match.details
    if len(details.round) > 20:
        raise ValueError(
            f"Historical round label exceeds database limit: {details.round!r}"
        )

    home_team = resolve_team(details.home_team)
    away_team = resolve_team(details.away_team)
    venue = resolve_venue(details.venue, SOURCE)
    start_date = historical_match_datetime(match, venue)

    game = Game(
        id=game_id,
        venue=venue,
        start_date=start_date,
        round=details.round,
        home_team=home_team,
        away_team=away_team,
        home_goals=details.home_team_goals,
        home_behinds=details.home_team_behinds,
        away_goals=details.away_team_goals,
        away_behinds=details.away_team_behinds,
    )

    def transform_stat(stat, team):
        player_id = player_id_map.get(stat.source_player_id)
        if player_id is None:
            raise ValueError(
                f"No canonical player mapping for {stat.player_name} "
                f"(AustralianFootball ID {stat.source_player_id}, "
                f"team {team}, year {details.date.year})"
            )
        return PlayerGameStats(
            player_id=player_id,
            team=team,
            jumper_number=stat.jumper_number,
            kicks=stat.kicks,
            marks=stat.marks,
            handballs=stat.handballs,
            goals=stat.goals,
            behinds=stat.behinds,
            hitouts=stat.hitouts,
            tackles=stat.tackles,
            rebound_50s=None,
            inside_50s=None,
            clearances=None,
            clangers=None,
            free_kicks_for=stat.free_kicks_for,
            free_kicks_against=stat.free_kicks_against,
            contested_possessions=None,
            uncontested_possessions=None,
            contested_marks=None,
            marks_inside_50=None,
            one_percenters=None,
            bounces=None,
            goal_assists=None,
            time_on_ground_percent=None,
            fantasy_points=None,
            game_id=game_id,
        )

    stats = [transform_stat(stat, home_team) for stat in match.home_team_stats]
    stats.extend(transform_stat(stat, away_team) for stat in match.away_team_stats)
    if len({stat.player_id for stat in stats}) != len(stats):
        raise ValueError(
            "Canonical player mapping aliases two participants in one game"
        )
    return game, stats
