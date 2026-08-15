"""Validated source models for historical AustralianFootball pages."""

from datetime import date, time
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .season import DiscoveredRound


SOURCE_NAME = "australian_football"
MIN_SUPPORTED_YEAR = 2006
MAX_SUPPORTED_YEAR = 2011

_EXPECTED_MATCH_COUNTS = {
    2006: 185,
    2007: 185,
    2008: 185,
    2009: 185,
    # The drawn grand final and replay add one match in 2010.
    2010: 186,
    # The 17-team competition played 187 home-and-away games plus finals.
    2011: 196,
}
_EXPECTED_GROUP_COUNTS = {
    2006: 31,
    2007: 31,
    2008: 31,
    2009: 31,
    2010: 32,
    2011: 33,
}


class AustralianFootballSeasonManifest(BaseModel):
    """Immutable match index discovered from one historical season page."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    source: Literal["australian_football"] = SOURCE_NAME
    year: int
    competition_id: Literal[138] = 138
    season_url: str = Field(min_length=1)
    discovered_at: AwareDatetime
    rounds: list[DiscoveredRound] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_source_contract(self):
        if self.year not in _EXPECTED_MATCH_COUNTS:
            raise ValueError(
                "AustralianFootball historical validation supports "
                f"{MIN_SUPPORTED_YEAR}-{MAX_SUPPORTED_YEAR}; got {self.year}"
            )

        labels = [round_.label for round_ in self.rounds]
        if len(labels) != len(set(labels)):
            raise ValueError("Historical season contains duplicate round labels")
        expected_groups = _EXPECTED_GROUP_COUNTS[self.year]
        if len(self.rounds) != expected_groups:
            raise ValueError(
                f"AustralianFootball season {self.year} contains "
                f"{len(self.rounds)} round/finals groups; expected reviewed "
                f"total {expected_groups}"
            )

        match_ids = self.match_ids
        if len(match_ids) != len(set(match_ids)):
            raise ValueError("A historical match appeared in more than one round")

        expected = _EXPECTED_MATCH_COUNTS[self.year]
        if len(match_ids) != expected:
            raise ValueError(
                f"AustralianFootball season {self.year} contains {len(match_ids)} "
                f"matches; expected reviewed total {expected}"
            )
        return self

    @property
    def match_ids(self) -> list[int]:
        return [match_id for round_ in self.rounds for match_id in round_.match_ids]

    @property
    def match_count(self) -> int:
        return len(self.match_ids)


class AustralianFootballMatchDetails(BaseModel):
    """Historical match metadata as published in local venue time."""

    model_config = ConfigDict(frozen=True)

    home_team: str = Field(min_length=1)
    away_team: str = Field(min_length=1)
    round: str = Field(min_length=1)
    date: date
    local_time: time
    venue: str = Field(min_length=1)
    status: Literal["FULL TIME"] = "FULL TIME"
    crowd: int | None = Field(default=None, ge=0)
    home_team_goals: int = Field(ge=0)
    home_team_behinds: int = Field(ge=0)
    home_team_total: int = Field(ge=0)
    away_team_goals: int = Field(ge=0)
    away_team_behinds: int = Field(ge=0)
    away_team_total: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_match(self):
        if self.home_team == self.away_team:
            raise ValueError("Home and away teams must differ")
        if self.home_team_goals * 6 + self.home_team_behinds != self.home_team_total:
            raise ValueError("Home score total does not equal goals * 6 + behinds")
        if self.away_team_goals * 6 + self.away_team_behinds != self.away_team_total:
            raise ValueError("Away score total does not equal goals * 6 + behinds")
        return self


class AustralianFootballPlayerStat(BaseModel):
    """The core match statistics actually published by AustralianFootball."""

    model_config = ConfigDict(frozen=True)

    source_player_id: str = Field(pattern=r"^\d+$")
    player_name: str = Field(min_length=1)
    jumper_number: int = Field(ge=0)
    kicks: int = Field(ge=0)
    marks: int = Field(ge=0)
    handballs: int = Field(ge=0)
    disposals: int = Field(ge=0)
    goals: int = Field(ge=0)
    behinds: int = Field(ge=0)
    hitouts: int = Field(ge=0)
    tackles: int = Field(ge=0)
    free_kicks_for: int = Field(ge=0)
    free_kicks_against: int = Field(ge=0)

    @field_validator("player_name")
    @classmethod
    def normalize_player_name(cls, value: str) -> str:
        normalized = " ".join(value.replace("\xa0", " ").split())
        if not normalized:
            raise ValueError("Player name must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_disposals(self):
        if self.kicks + self.handballs != self.disposals:
            raise ValueError("Disposals do not equal kicks + handballs")
        return self


class AustralianFootballMatchData(BaseModel):
    """One historical match, retaining source-specific player identities."""

    model_config = ConfigDict(frozen=True)

    details: AustralianFootballMatchDetails
    home_team_stats: list[AustralianFootballPlayerStat] = Field(min_length=1)
    away_team_stats: list[AustralianFootballPlayerStat] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_player_identity(self):
        home_ids = [stat.source_player_id for stat in self.home_team_stats]
        away_ids = [stat.source_player_id for stat in self.away_team_stats]
        if len(home_ids) != len(set(home_ids)):
            raise ValueError("Home statistics contain duplicate source player IDs")
        if len(away_ids) != len(set(away_ids)):
            raise ValueError("Away statistics contain duplicate source player IDs")
        overlap = sorted(set(home_ids) & set(away_ids))
        if overlap:
            raise ValueError(f"Players appeared for both teams: {overlap}")
        return self


class CachedAustralianFootballMatch(BaseModel):
    """Versioned cache envelope binding data to its source match identity."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    source: Literal["australian_football"] = SOURCE_NAME
    match_id: int = Field(gt=0)
    source_url: str = Field(min_length=1)
    scraped_at: AwareDatetime
    data: AustralianFootballMatchData
