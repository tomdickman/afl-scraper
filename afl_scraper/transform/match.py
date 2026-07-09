import json
import re
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from ..models.game import Game
from ..models.player_game_stats import PlayerGameStats
from ..transformer.teams import transform_team_name


def _load_jsonc(path: Path) -> dict:
    text = path.read_text()
    text = re.sub(r"//.*", "", text)
    return json.loads(text)


def _load_venue_mappings(source: str) -> dict[str, str]:
    path = Path("config/venue_name_mappings.jsonc")
    data = _load_jsonc(path)
    return data.get(source, {})


def resolve_venue(venue_name: str, source: str = "afl_official") -> str:
    mappings = _load_venue_mappings(source)

    if venue_name in mappings:
        return mappings[venue_name]

    venue_lower = venue_name.lower().strip()
    for key, val in mappings.items():
        if key.lower().strip() == venue_lower:
            return val

    collapsed = re.sub(r"\s+", "", venue_name).lower()
    for key, val in mappings.items():
        if re.sub(r"\s+", "", key).lower() == collapsed:
            return val

    raise KeyError(f"No venue mapping found for '{venue_name}' (source: {source})")


def resolve_team(team_name: str) -> str:
    return transform_team_name(team_name)


_DATETIME_FORMATS = [
    "%a %d %b %Y %I:%M%p",
    "%a %d %b %Y %H:%M",
    "%d %b %Y %I:%M%p",
    "%d %b %Y %H:%M",
]


def parse_match_datetime(date_str: str, time_str: str) -> datetime:
    combined = f"{date_str} {time_str}".strip()
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(combined, fmt)
        except ValueError:
            continue
    raise ValueError(f"Could not parse match datetime: date='{date_str}' time='{time_str}'")


_COLUMN_MAPPING = {
    "#": "jumper_number",
    "K": "kicks",
    "HB": "handballs",
    "M": "marks",
    "G": "goals",
    "B": "behinds",
    "HO": "hitouts",
    "T": "tackles",
    "R50": "rebound_50s",
    "I50": "inside_50s",
    "CL": "clearances",
    "CG": "clangers",
    "FF": "free_kicks_for",
    "FA": "free_kicks_against",
    "CP": "contested_possessions",
    "UP": "uncontested_possessions",
    "CM": "contested_marks",
    "MI5": "marks_inside_50",
    "1%": "one_percenters",
    "BO": "bounces",
    "GA": "goal_assists",
    "TOG%": "time_on_ground_percent",
    "AF": "fantasy_points",
}


def _norm_col(name: str) -> str:
    return name.strip().upper()


def _stats_row_to_pgs(
    row: pd.Series,
    team_id: str,
    game_id: int,
    player_game_number: int,
    resolve_player_id: Callable[[str, str], str | None],
) -> PlayerGameStats | None:
    player_name = str(row.iloc[0]).strip()
    if not player_name:
        return None

    player_id = resolve_player_id(player_name, team_id) if resolve_player_id else player_name

    cols = {_norm_col(k): v for k, v in _COLUMN_MAPPING.items()}
    vals: dict[str, int | Decimal] = {}

    for raw_name, raw_val in row.items():
        field = cols.get(_norm_col(raw_name))
        if field is None:
            continue
        s = str(raw_val).strip()
        if s == "" or s == "-":
            s = "0"
        if field == "time_on_ground_percent":
            vals[field] = Decimal(s.rstrip("%"))
        else:
            vals[field] = int(s)

    return PlayerGameStats(
        player_id=player_id,
        player_game_number=player_game_number,
        team=team_id,
        jumper_number=vals.get("jumper_number", 0),
        kicks=vals.get("kicks", 0),
        marks=vals.get("marks", 0),
        handballs=vals.get("handballs", 0),
        goals=vals.get("goals", 0),
        behinds=vals.get("behinds", 0),
        hitouts=vals.get("hitouts", 0),
        tackles=vals.get("tackles", 0),
        rebound_50s=vals.get("rebound_50s", 0),
        inside_50s=vals.get("inside_50s", 0),
        clearances=vals.get("clearances", 0),
        clangers=vals.get("clangers", 0),
        free_kicks_for=vals.get("free_kicks_for", 0),
        free_kicks_against=vals.get("free_kicks_against", 0),
        contested_possessions=vals.get("contested_possessions", 0),
        uncontested_possessions=vals.get("uncontested_possessions", 0),
        contested_marks=vals.get("contested_marks", 0),
        marks_inside_50=vals.get("marks_inside_50", 0),
        one_percenters=vals.get("one_percenters", 0),
        bounces=vals.get("bounces", 0),
        goal_assists=vals.get("goal_assists", 0),
        time_on_ground_percent=vals.get("time_on_ground_percent", Decimal("0")),
        fantasy_points=vals.get("fantasy_points", 0),
        game_id=game_id,
    )


def transform_match(
    raw_data: dict,
    match_id: int,
    source: str = "afl_official",
    resolve_player_id: Callable[[str, str], str | None] | None = None,
) -> tuple[Game, list[PlayerGameStats]]:
    details = raw_data["details"]

    home_team_id = resolve_team(details["home_team"])
    away_team_id = resolve_team(details["away_team"])
    venue_id = resolve_venue(details["venue"], source)
    start_date = parse_match_datetime(details["date"], details["time"])

    game = Game(
        id=match_id,
        venue=venue_id,
        start_date=start_date,
        round=details["round"],
        home_team=home_team_id,
        away_team=away_team_id,
        home_goals=details["home_team_goals"],
        home_behinds=details["home_team_behinds"],
        away_goals=details["away_team_goals"],
        away_behinds=details["away_team_behinds"],
    )

    player_stats: list[PlayerGameStats] = []

    for i, (_, row) in enumerate(raw_data["home_team_stats"].iterrows()):
        pgs = _stats_row_to_pgs(row, home_team_id, match_id, i + 1, resolve_player_id)
        if pgs:
            player_stats.append(pgs)

    for i, (_, row) in enumerate(raw_data["away_team_stats"].iterrows()):
        pgs = _stats_row_to_pgs(row, away_team_id, match_id, i + 1, resolve_player_id)
        if pgs:
            player_stats.append(pgs)

    return (game, player_stats)
