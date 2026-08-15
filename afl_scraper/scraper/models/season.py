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

    schema_version: Literal[1] = 1
    source: Literal["afl_official"] = "afl_official"
    year: int
    season_id: int = Field(gt=0)
    fixture_url: str = Field(min_length=1)
    discovered_at: AwareDatetime
    rounds: list[DiscoveredRound] = Field(min_length=1)

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
        return self

    @property
    def match_count(self) -> int:
        return sum(len(round_.match_ids) for round_ in self.rounds)
