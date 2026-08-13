from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Player(BaseModel):
    """A database player record transformed from AFL Tables."""

    id: str
    givenname: str
    familyname: str
    birthdate: datetime


class PlayerInfo(BaseModel):
    """A player record scraped from a data source."""

    id: str
    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")
    team: str
    year: int

    model_config = ConfigDict(populate_by_name=True)

    def display_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class PlayerMatch(BaseModel):
    """An exact name+team match between two sources."""

    afl: PlayerInfo
    tables: PlayerInfo


class FuzzyMatch(BaseModel):
    """A name match with team mismatch, presenting multiple candidates."""

    afl: PlayerInfo
    tables: list[PlayerInfo]


class MatchResult(BaseModel):
    """Full match categorisation between two player lists."""

    exact: list[PlayerMatch]
    fuzzy: list[FuzzyMatch]
    unmatched_afl: list[PlayerInfo]
    unmatched_tables: list[PlayerInfo]


class PlayerMapping(BaseModel):
    """A mapping between an AFL official ID and an AFL Tables ID."""

    afl_official_id: str | None = None
    player_id: str = Field(min_length=1)

    @field_validator("afl_official_id", "player_id", mode="before")
    @classmethod
    def strip_ids(cls, value: str | None) -> str | None:
        """Reject blank IDs and keep persisted mapping identifiers canonical."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("mapping IDs must be strings")
        value = value.strip()
        if not value:
            raise ValueError("mapping IDs must not be blank")
        return value
