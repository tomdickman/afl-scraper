"""Round-level orchestration with typed per-match outcomes."""

from dataclasses import dataclass

from ..scraper import (
    load_season_manifest,
    scrape_match,
    scrape_match_ids,
    sync_browser_context,
)
from ..scraper.models import RawMatchData
from .match import load_match_data


@dataclass(frozen=True)
class RoundMatchResult:
    match_id: int
    raw_data: RawMatchData | None = None
    loaded: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def round_pipeline(
    round_number: str,
    year: int | None = None,
    headless: bool = True,
    load: bool = True,
    progress=None,
) -> list[RoundMatchResult]:
    """Process a round while isolating and reporting individual match failures."""
    results = []

    with sync_browser_context(headless) as browser:
        ids = scrape_match_ids(browser, round_number, year)
        try:
            manifest = load_season_manifest(year)
        except FileNotFoundError:
            manifest = None
        if progress is not None:
            progress("discovered", None, f"{len(ids)} matches")

        for match_id in ids:
            try:
                raw_data = scrape_match(
                    browser,
                    match_id,
                    expected_year=year,
                    fixture=manifest.fixture_for(match_id) if manifest else None,
                )
                if load:
                    load_match_data(raw_data, int(match_id))
                results.append(
                    RoundMatchResult(
                        match_id=int(match_id), raw_data=raw_data, loaded=load
                    )
                )
                if progress is not None:
                    progress("completed", match_id, None)
            except Exception as error:
                results.append(RoundMatchResult(int(match_id), error=str(error)))
                if progress is not None:
                    progress("failed", match_id, str(error))

    return results
