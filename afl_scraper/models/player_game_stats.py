from decimal import Decimal

from .db import DBModel


class PlayerGameStats(DBModel):
    __table_name__ = "player_game_stats"
    __conflict_cols__ = ["player_id", "game_id"]
    __exclude_updates_cols__ = []
    # The current AFL table no longer publishes these fields. A non-null value
    # can enrich a row, but replaying a sparse source must not erase one.
    __preserve_existing_on_null_cols__ = [
        "rebound_50s",
        "inside_50s",
        "clearances",
        "clangers",
        "free_kicks_for",
        "free_kicks_against",
        "contested_possessions",
        "uncontested_possessions",
        "contested_marks",
        "marks_inside_50",
        "one_percenters",
        "bounces",
        "goal_assists",
        "time_on_ground_percent",
        "fantasy_points",
    ]

    player_id: str
    team: str
    jumper_number: int
    kicks: int
    marks: int
    handballs: int
    goals: int
    behinds: int
    hitouts: int
    tackles: int
    rebound_50s: int | None
    inside_50s: int | None
    clearances: int | None
    clangers: int | None
    free_kicks_for: int | None
    free_kicks_against: int | None
    contested_possessions: int | None
    uncontested_possessions: int | None
    contested_marks: int | None
    marks_inside_50: int | None
    one_percenters: int | None
    bounces: int | None
    goal_assists: int | None
    time_on_ground_percent: Decimal | None
    fantasy_points: int | None
    game_id: int
