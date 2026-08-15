"""Versioned envelope for validated raw match caches."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .raw_match import RawMatchData


class CachedRawMatch(BaseModel):
    """A validated match bound to its source identity and scrape time."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    source: Literal["afl_official"] = "afl_official"
    match_id: int = Field(gt=0)
    source_url: str = Field(min_length=1)
    scraped_at: AwareDatetime
    data: RawMatchData
