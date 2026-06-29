from datetime import datetime

from .db import DBModel


class Game(DBModel):
    __table_name__ = "game"
    __conflict_cols__ = ["id"]
    __exclude_updates_cols__ = []

    id: int
    venue: str
    start_date: datetime
    round: str
    home_team: str
    away_team: str
    home_goals: int
    home_behinds: int
    away_goals: int
    away_behinds: int
