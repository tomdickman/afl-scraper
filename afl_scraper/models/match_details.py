from dataclasses import dataclass

@dataclass
class RawMatchDetails:
    home_team: str
    away_team: str
    round: str
    date: str
    time: str
    venue: str
