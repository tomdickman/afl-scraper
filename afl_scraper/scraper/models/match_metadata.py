"""Source-qualified match metadata and provenance models."""

from datetime import date, time
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class MatchMetadataRecord(BaseModel):
    """One validated match metadata record from AFL Tables."""

    model_config = ConfigDict(frozen=True)

    source: Literal["afl_tables"] = "afl_tables"
    source_match_id: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    year: int
    round: str = Field(min_length=1)
    home_team: str = Field(min_length=1)
    away_team: str = Field(min_length=1)
    local_date: date
    local_time: time
    venue: str = Field(min_length=1)
    home_goals: int = Field(ge=0)
    home_behinds: int = Field(ge=0)
    home_total: int = Field(ge=0)
    away_goals: int = Field(ge=0)
    away_behinds: int = Field(ge=0)
    away_total: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_match(self):
        if self.local_date.year != self.year:
            raise ValueError("Match metadata date does not belong to its season")
        if self.home_team == self.away_team:
            raise ValueError("Match metadata teams must differ")
        if self.home_goals * 6 + self.home_behinds != self.home_total:
            raise ValueError("Home metadata score total is inconsistent")
        if self.away_goals * 6 + self.away_behinds != self.away_total:
            raise ValueError("Away metadata score total is inconsistent")
        return self


class MatchMetadataCatalog(BaseModel):
    """Atomic, year-scoped AFL Tables match catalogue."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    source: Literal["afl_tables"] = "afl_tables"
    year: int
    source_url: str = Field(min_length=1)
    fetched_at: AwareDatetime
    matches: list[MatchMetadataRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_catalog(self):
        wrong_year = sorted(
            {item.year for item in self.matches if item.year != self.year}
        )
        if wrong_year:
            raise ValueError(f"Metadata catalogue contains years {wrong_year}")
        source_ids = [item.source_match_id for item in self.matches]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Metadata catalogue contains duplicate source match IDs")
        return self


class MatchDataProvenance(BaseModel):
    """Evidence explaining how a combined raw match was assembled."""

    model_config = ConfigDict(frozen=True)

    player_stats_source: Literal["afl_official", "afl_tables"] = "afl_official"
    player_stats_url: str = Field(min_length=1)
    match_details_source: Literal["afl_official", "afl_tables"]
    match_details_url: str = Field(min_length=1)
    official_fixture_url: str | None = None
    cross_checked_fields: tuple[str, ...] = ()
    fallback_reason: str | None = None
