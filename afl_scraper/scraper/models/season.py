"""Validated season-discovery artifacts."""

from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from ..constants import official_season_id


class OfficialFixtureMetadata(BaseModel):
    """Identity evidence retained from one AFL Official fixture card."""

    model_config = ConfigDict(frozen=True)

    match_id: int = Field(gt=0)
    provider_id: str | None = None
    round: str = Field(min_length=1)
    home_team: str = Field(min_length=1)
    away_team: str = Field(min_length=1)
    scheduled_at: AwareDatetime | None = None
    venue: str | None = None
    home_total: int | None = Field(default=None, ge=0)
    away_total: int | None = Field(default=None, ge=0)
    status: str = Field(min_length=1)
    source_url: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_fixture(self):
        if self.home_team == self.away_team:
            raise ValueError("Fixture teams must differ")
        if (self.home_total is None) != (self.away_total is None):
            raise ValueError("Fixture must contain both score totals or neither")
        return self


class DiscoveredRound(BaseModel):
    """One source round and its ordered match IDs."""

    model_config = ConfigDict(frozen=True)

    label: str = Field(min_length=1)
    match_ids: list[int] = Field(min_length=1)

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Round labels must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_match_ids(self):
        if any(match_id <= 0 for match_id in self.match_ids):
            raise ValueError("Season match IDs must be positive")
        if len(self.match_ids) != len(set(self.match_ids)):
            raise ValueError(f"Round {self.label!r} contains duplicate match IDs")
        return self


class SeasonManifest(BaseModel):
    """Immutable description of matches exposed for one official season."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1, 2] = 1
    source: Literal["afl_official"] = "afl_official"
    year: int
    season_id: int = Field(gt=0)
    fixture_url: str = Field(min_length=1)
    discovered_at: AwareDatetime
    rounds: list[DiscoveredRound] = Field(min_length=1)
    fixtures: list[OfficialFixtureMetadata] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_rounds_and_matches(self):
        expected_season_id = official_season_id(self.year)
        if self.season_id != expected_season_id:
            raise ValueError(
                f"Season {self.year} must use reviewed official ID "
                f"{expected_season_id}; got {self.season_id}"
            )
        labels = [round_.label for round_ in self.rounds]
        if len(labels) != len(set(labels)):
            raise ValueError("Season manifest contains duplicate round labels")

        all_ids = [match_id for round_ in self.rounds for match_id in round_.match_ids]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("A match ID appeared in more than one round")
        if self.schema_version == 2 and not self.fixtures:
            raise ValueError("Schema-version-2 manifests require fixture metadata")
        if self.schema_version == 1 and self.fixtures:
            raise ValueError(
                "Schema-version-1 manifests cannot contain fixture metadata"
            )
        if self.fixtures:
            fixture_ids = [fixture.match_id for fixture in self.fixtures]
            if len(fixture_ids) != len(set(fixture_ids)):
                raise ValueError("Season manifest contains duplicate fixture metadata")
            if set(fixture_ids) != set(all_ids):
                raise ValueError(
                    "Season fixture metadata must exactly cover discovered match IDs"
                )
        return self

    @property
    def match_count(self) -> int:
        return sum(len(round_.match_ids) for round_ in self.rounds)

    @property
    def match_ids(self) -> list[int]:
        """Return every season match ID in source round order."""
        return [match_id for round_ in self.rounds for match_id in round_.match_ids]

    def fixture_for(self, match_id: int) -> OfficialFixtureMetadata | None:
        return next(
            (fixture for fixture in self.fixtures if fixture.match_id == match_id),
            None,
        )
