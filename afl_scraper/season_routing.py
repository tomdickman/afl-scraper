"""Central year-to-source routing for season workflows."""

from dataclasses import dataclass
from pathlib import Path

from .scraper.constants import (
    MAX_CONFIGURED_YEAR,
    MIN_HISTORY_YEAR,
    OFFICIAL_FIXTURE_MIN_YEAR,
)


@dataclass(frozen=True)
class SeasonPlan:
    """Provider choices and artifact locations for one configured season."""

    year: int
    match_source: str
    display_source: str
    sparse_player_stats: bool

    @property
    def approved_mapping_path(self) -> Path:
        if self.match_source == "australian_football":
            return Path(f"data/mapping/{self.year}_australian_football_approved.json")
        return Path(f"data/mapping/{self.year}_approved.json")

    @property
    def review_mapping_path(self) -> Path:
        if self.match_source == "australian_football":
            return Path(f"data/mapping/{self.year}_australian_football_to_review.json")
        return Path(f"data/mapping/{self.year}_to_review.json")


def season_plan(year: int) -> SeasonPlan:
    """Resolve a configured year without leaking era checks into callers."""
    if year < MIN_HISTORY_YEAR or year > MAX_CONFIGURED_YEAR:
        raise ValueError(
            f"Season year must be between {MIN_HISTORY_YEAR} and "
            f"{MAX_CONFIGURED_YEAR}; got {year}"
        )
    if year < OFFICIAL_FIXTURE_MIN_YEAR:
        return SeasonPlan(
            year=year,
            match_source="australian_football",
            display_source="AustralianFootball",
            sparse_player_stats=True,
        )
    return SeasonPlan(
        year=year,
        match_source="afl_official",
        display_source="AFL Official",
        sparse_player_stats=False,
    )


def season_years(start_year: int, end_year: int) -> list[int]:
    """Validate and expand an inclusive configured season range."""
    if start_year > end_year:
        raise ValueError("Season start year must not exceed end year")
    season_plan(start_year)
    season_plan(end_year)
    return list(range(start_year, end_year + 1))
