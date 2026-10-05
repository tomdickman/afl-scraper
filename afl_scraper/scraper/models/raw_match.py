from decimal import Decimal
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RawMatchDetails(BaseModel):
    """Validated match metadata extracted from the AFL match centre."""

    model_config = ConfigDict(frozen=True)

    home_team: str = Field(min_length=1)
    away_team: str = Field(min_length=1)
    round: str = Field(min_length=1)
    date: str = Field(min_length=1)
    time: str = Field(min_length=1)
    venue: str = Field(min_length=1)
    status: Literal["FULL TIME"]
    home_team_goals: int = Field(ge=0)
    home_team_behinds: int = Field(ge=0)
    home_team_total: int = Field(ge=0)
    away_team_goals: int = Field(ge=0)
    away_team_behinds: int = Field(ge=0)
    away_team_total: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_match_invariants(self):
        if self.home_team == self.away_team:
            raise ValueError("Home and away teams must differ")
        if self.home_team_goals * 6 + self.home_team_behinds != self.home_team_total:
            raise ValueError("Home score total does not equal goals * 6 + behinds")
        if self.away_team_goals * 6 + self.away_team_behinds != self.away_team_total:
            raise ValueError("Away score total does not equal goals * 6 + behinds")
        return self


class RawPlayerStat(BaseModel):
    """Source-normalised statistics for one player in one AFL match."""

    model_config = ConfigDict(frozen=True)

    afl_official_id: str = Field(pattern=r"^\d+$")
    player_name: str = Field(min_length=1)
    jumper_number: int = Field(ge=0)
    kicks: int = Field(ge=0)
    handballs: int = Field(ge=0)
    marks: int = Field(ge=0)
    goals: int = Field(ge=0)
    behinds: int = Field(ge=0)
    hitouts: int = Field(ge=0)
    tackles: int = Field(ge=0)
    clearances: int = Field(ge=0)
    goal_assists: int = Field(ge=0)
    time_on_ground_percent: Decimal = Field(ge=0, le=100)
    fantasy_points: int = Field(ge=0)
    disposals: int | None = Field(default=None, ge=0)
    # Metres gained is a net field-position measure and can be negative.
    metres_gained: int | None = None
    rebound_50s: int | None = Field(default=None, ge=0)
    inside_50s: int | None = Field(default=None, ge=0)
    clangers: int | None = Field(default=None, ge=0)
    free_kicks_for: int | None = Field(default=None, ge=0)
    free_kicks_against: int | None = Field(default=None, ge=0)
    contested_possessions: int | None = Field(default=None, ge=0)
    uncontested_possessions: int | None = Field(default=None, ge=0)
    contested_marks: int | None = Field(default=None, ge=0)
    marks_inside_50: int | None = Field(default=None, ge=0)
    one_percenters: int | None = Field(default=None, ge=0)
    bounces: int | None = Field(default=None, ge=0)
    extra_stats: dict[str, str] = Field(default_factory=dict)

    @field_validator("player_name")
    @classmethod
    def normalize_player_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Player name must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_disposals(self):
        if self.disposals is not None and self.kicks + self.handballs != self.disposals:
            raise ValueError("Disposals do not equal kicks + handballs")
        return self


class RawMatchData(BaseModel):
    """Canonical extraction result with DataFrame views for analysis."""

    model_config = ConfigDict(frozen=True)

    details: RawMatchDetails
    home_team_stats: list[RawPlayerStat] = Field(min_length=1)
    away_team_stats: list[RawPlayerStat] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_player_identity(self):
        home_ids = [stat.afl_official_id for stat in self.home_team_stats]
        away_ids = [stat.afl_official_id for stat in self.away_team_stats]
        if len(home_ids) != len(set(home_ids)):
            raise ValueError("Home player statistics contain duplicate official IDs")
        if len(away_ids) != len(set(away_ids)):
            raise ValueError("Away player statistics contain duplicate official IDs")
        overlap = sorted(set(home_ids) & set(away_ids))
        if overlap:
            raise ValueError(f"Players appeared for both teams: {overlap}")
        return self

    def home_stats_dataframe(self) -> pd.DataFrame:
        return self._to_dataframe(self.home_team_stats)

    def away_stats_dataframe(self) -> pd.DataFrame:
        return self._to_dataframe(self.away_team_stats)

    @staticmethod
    def _to_dataframe(stats: list[RawPlayerStat]) -> pd.DataFrame:
        return pd.DataFrame(player.model_dump() for player in stats)
