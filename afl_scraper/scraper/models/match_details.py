from dataclasses import dataclass
import pandas as pd


@dataclass
class RawMatchDetails:
    home_team: str
    away_team: str
    round: str
    date: str
    day: str
    time: str
    venue: str
    year: int
    home_team_goals: int
    home_team_behinds: int
    home_team_total: int
    away_team_goals: int
    away_team_behinds: int
    away_team_total: int

@dataclass
class RawMatchData:
    details: RawMatchDetails
    home_team_stats: pd.DataFrame
    away_team_stats: pd.DataFrame
