"""Versioned operator artifacts for historical backfill orchestration."""

from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    model_validator,
)


class HistoricalReconciliationReport(BaseModel):
    """Expected cache records compared with source-qualified database rows."""

    model_config = ConfigDict(frozen=True)

    year: int
    expected_matches: int = Field(ge=0)
    database_matches: int = Field(ge=0)
    expected_player_stats: int = Field(ge=0)
    database_player_stats: int = Field(ge=0)
    missing_match_ids: list[str] = Field(default_factory=list)
    unexpected_match_ids: list[str] = Field(default_factory=list)
    missing_player_stats: list[str] = Field(default_factory=list)
    unexpected_player_stats: list[str] = Field(default_factory=list)
    value_mismatches: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def ok(self) -> bool:
        return not any(
            (
                self.missing_match_ids,
                self.unexpected_match_ids,
                self.missing_player_stats,
                self.unexpected_player_stats,
                self.value_mismatches,
            )
        )

    @computed_field
    @property
    def mismatch_count(self) -> int:
        return sum(
            len(items)
            for items in (
                self.missing_match_ids,
                self.unexpected_match_ids,
                self.missing_player_stats,
                self.unexpected_player_stats,
                self.value_mismatches,
            )
        )


class HistoricalBackfillYear(BaseModel):
    """Durable state for one year in a multi-year run."""

    status: Literal["pending", "validated", "loaded", "verified", "failed"]
    expected_matches: int = Field(default=0, ge=0)
    expected_player_stats: int = Field(default=0, ge=0)
    database_matches: int = Field(default=0, ge=0)
    database_player_stats: int = Field(default=0, ge=0)
    differences: int = Field(default=0, ge=0)
    inserted_games: int = Field(default=0, ge=0)
    updated_games: int = Field(default=0, ge=0)
    completed_at: AwareDatetime | None = None
    error: str | None = None


class HistoricalBackfillCheckpoint(BaseModel):
    """Atomically replaced progress record for one exact year range."""

    schema_version: Literal[1] = 1
    source: Literal["australian_football"] = "australian_football"
    start_year: int
    end_year: int
    created_at: AwareDatetime
    updated_at: AwareDatetime
    years: dict[int, HistoricalBackfillYear]

    @model_validator(mode="after")
    def validate_range(self):
        if self.start_year > self.end_year:
            raise ValueError("Historical checkpoint start year exceeds end year")
        expected = set(range(self.start_year, self.end_year + 1))
        if set(self.years) != expected:
            raise ValueError("Historical checkpoint years do not match its range")
        return self


class HistoricalBackfillReport(BaseModel):
    """Latest analytical reconciliation summary for a range run."""

    schema_version: Literal[1] = 1
    source: Literal["australian_football"] = "australian_football"
    start_year: int
    end_year: int
    dry_run: bool
    resume: bool
    generated_at: AwareDatetime
    years: list[HistoricalReconciliationReport]

    @model_validator(mode="after")
    def validate_years(self):
        observed = [year.year for year in self.years]
        if len(observed) != len(set(observed)):
            raise ValueError("Historical report contains duplicate years")
        if any(year < self.start_year or year > self.end_year for year in observed):
            raise ValueError("Historical report contains a year outside its range")
        return self

    @computed_field
    @property
    def complete(self) -> bool:
        return len(self.years) == self.end_year - self.start_year + 1

    @computed_field
    @property
    def expected_matches(self) -> int:
        return sum(year.expected_matches for year in self.years)

    @computed_field
    @property
    def database_matches(self) -> int:
        return sum(year.database_matches for year in self.years)

    @computed_field
    @property
    def expected_player_stats(self) -> int:
        return sum(year.expected_player_stats for year in self.years)

    @computed_field
    @property
    def database_player_stats(self) -> int:
        return sum(year.database_player_stats for year in self.years)

    @computed_field
    @property
    def mismatch_count(self) -> int:
        return sum(year.mismatch_count for year in self.years)

    @computed_field
    @property
    def ok(self) -> bool:
        return self.complete and all(year.ok for year in self.years)
