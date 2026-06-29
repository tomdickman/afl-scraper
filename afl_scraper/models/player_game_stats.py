from decimal import Decimal

from .db import DBModel


class PlayerGameStats(DBModel):
    __table_name__ = "player_game_stats"
    __conflict_cols__ = ["player_id", "player_game_number"]
    __exclude_updates_cols__ = []

    player_id: str
    player_game_number: int
    team: str
    jumper_number: int
    kicks: int
    marks: int
    handballs: int
    goals: int
    behinds: int
    hitouts: int
    tackles: int
    rebound_50s: int
    inside_50s: int
    clearances: int
    clangers: int
    free_kicks_for: int
    free_kicks_against: int
    contested_possessions: int
    uncontested_possessions: int
    contested_marks: int
    marks_inside_50: int
    one_percenters: int
    bounces: int
    goal_assists: int
    time_on_ground_percent: Decimal
    fantasy_points: int
    game_id: int
