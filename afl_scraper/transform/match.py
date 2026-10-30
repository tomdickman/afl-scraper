from collections.abc import Callable
from datetime import datetime

from ..models.game import Game
from ..models.player_game_stats import PlayerGameStats
from ..normalization import canonical_team, canonical_venue, parse_aware_datetime
from ..rounds import normalize_round_label
from ..scraper.models import RawMatchData, RawPlayerStat

PlayerIdResolver = Callable[[RawPlayerStat, str, int], str | None]


def resolve_venue(venue_name: str, source: str = "afl_official") -> str:
    return canonical_venue(venue_name, source)


def resolve_team(team_name: str) -> str:
    return canonical_team(team_name)


def parse_match_datetime(date_str: str, time_str: str) -> datetime:
    return parse_aware_datetime(date_str, time_str)


def _stats_to_player_game_stats(
    stat: RawPlayerStat,
    team_id: str,
    game_id: int,
    match_year: int,
    resolve_player_id: PlayerIdResolver | None,
) -> PlayerGameStats:
    player_id = (
        resolve_player_id(stat, team_id, match_year)
        if resolve_player_id
        else stat.afl_official_id
    )
    if player_id is None:
        raise ValueError(
            "No canonical player mapping for "
            f"{stat.player_name} (AFL official ID {stat.afl_official_id}, "
            f"team {team_id}, year {match_year})"
        )

    return PlayerGameStats(
        player_id=player_id,
        team=team_id,
        jumper_number=stat.jumper_number,
        kicks=stat.kicks,
        marks=stat.marks,
        handballs=stat.handballs,
        goals=stat.goals,
        behinds=stat.behinds,
        hitouts=stat.hitouts,
        tackles=stat.tackles,
        rebound_50s=stat.rebound_50s,
        inside_50s=stat.inside_50s,
        clearances=stat.clearances,
        clangers=stat.clangers,
        free_kicks_for=stat.free_kicks_for,
        free_kicks_against=stat.free_kicks_against,
        contested_possessions=stat.contested_possessions,
        uncontested_possessions=stat.uncontested_possessions,
        contested_marks=stat.contested_marks,
        marks_inside_50=stat.marks_inside_50,
        one_percenters=stat.one_percenters,
        bounces=stat.bounces,
        goal_assists=stat.goal_assists,
        time_on_ground_percent=stat.time_on_ground_percent,
        fantasy_points=stat.fantasy_points,
        game_id=game_id,
    )


def transform_match(
    raw_data: RawMatchData | dict,
    match_id: int,
    source: str = "afl_official",
    resolve_player_id: PlayerIdResolver | None = None,
) -> tuple[Game, list[PlayerGameStats]]:
    raw_match = RawMatchData.model_validate(raw_data)
    details = raw_match.details

    home_team_id = resolve_team(details.home_team)
    away_team_id = resolve_team(details.away_team)
    venue_id = resolve_venue(details.venue, source)
    start_date = parse_match_datetime(details.date, details.time)

    game = Game(
        id=match_id,
        venue=venue_id,
        start_date=start_date,
        round=normalize_round_label(details.round),
        home_team=home_team_id,
        away_team=away_team_id,
        home_goals=details.home_team_goals,
        home_behinds=details.home_team_behinds,
        away_goals=details.away_team_goals,
        away_behinds=details.away_team_behinds,
    )

    player_stats = [
        _stats_to_player_game_stats(
            stat,
            home_team_id,
            match_id,
            start_date.year,
            resolve_player_id,
        )
        for stat in raw_match.home_team_stats
    ]
    player_stats.extend(
        _stats_to_player_game_stats(
            stat,
            away_team_id,
            match_id,
            start_date.year,
            resolve_player_id,
        )
        for stat in raw_match.away_team_stats
    )
    return game, player_stats
