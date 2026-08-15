import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..models.game import Game
from ..models.player_game_stats import PlayerGameStats
from ..scraper.models import RawMatchData, RawPlayerStat
from ..transformer.teams import transform_team_name


PlayerIdResolver = Callable[[RawPlayerStat, str, int], str | None]


def _load_jsonc(path: Path) -> dict:
    text = path.read_text()
    text = re.sub(r"//.*", "", text)
    return json.loads(text)


def _load_venue_mappings(source: str) -> dict[str, str]:
    path = Path(__file__).resolve().parents[2] / "config/venue_name_mappings.jsonc"
    data = _load_jsonc(path)
    return data.get(source, {})


def _normalize_venue(value: str, *, collapse_spaces: bool = False) -> str:
    normalized = " ".join(value.replace("\xa0", " ").split()).casefold()
    return normalized.replace(" ", "") if collapse_spaces else normalized


def resolve_venue(venue_name: str, source: str = "afl_official") -> str:
    mappings = _load_venue_mappings(source)
    cleaned = " ".join(venue_name.replace("\xa0", " ").split()).strip(" ,")
    candidates = [cleaned]
    if "," in cleaned:
        candidates.append(cleaned.rsplit(",", 1)[0].strip())

    for candidate in candidates:
        for key, value in mappings.items():
            if _normalize_venue(key) == _normalize_venue(candidate):
                return value
            if _normalize_venue(key, collapse_spaces=True) == _normalize_venue(
                candidate, collapse_spaces=True
            ):
                return value

    raise KeyError(f"No venue mapping found for '{venue_name}' (source: {source})")


def resolve_team(team_name: str) -> str:
    return transform_team_name(team_name)


_DATE_FORMATS = ["%A %d %B %Y", "%a %d %b %Y", "%d %b %Y"]
_CLOCK_FORMATS = ["%I:%M %p", "%I:%M%p", "%H:%M"]
_TIMEZONE_PATTERN = re.compile(
    r"^(?P<clock>.+?)\s*\(GMT(?P<sign>[+-])(?P<hours>\d{1,2})"
    r"(?::?(?P<minutes>\d{2}))?\)$",
    re.IGNORECASE,
)


def parse_match_datetime(date_str: str, time_str: str) -> datetime:
    normalized_date = " ".join(date_str.split())
    normalized_time = " ".join(time_str.split())
    timezone_match = _TIMEZONE_PATTERN.fullmatch(normalized_time)
    if timezone_match is None:
        raise ValueError(f"Match time must include a numeric GMT offset: {time_str!r}")

    hours = int(timezone_match.group("hours"))
    minutes = int(timezone_match.group("minutes") or "0")
    if hours > 14 or minutes >= 60:
        raise ValueError(f"Invalid GMT offset in match time: {time_str!r}")
    direction = 1 if timezone_match.group("sign") == "+" else -1
    offset = timezone(direction * timedelta(hours=hours, minutes=minutes))
    clock = timezone_match.group("clock").strip()

    for date_format in _DATE_FORMATS:
        for clock_format in _CLOCK_FORMATS:
            try:
                parsed = datetime.strptime(
                    f"{normalized_date} {clock}", f"{date_format} {clock_format}"
                )
                return parsed.replace(tzinfo=offset)
            except ValueError:
                continue
    raise ValueError(
        f"Could not parse match datetime: date={date_str!r} time={time_str!r}"
    )


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
        round=details.round,
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
