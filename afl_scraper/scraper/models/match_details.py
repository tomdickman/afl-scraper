from dataclasses import dataclass
import pandas as pd


@dataclass
class RawMatchDetails:
    home_team: str
    away_team: str
    round: str
    date: str
    time: str
    venue: str


@dataclass
class RawMatchData:
    details: RawMatchDetails
    home_team_stats: pd.DataFrame
    away_team_stats: pd.DataFrame
