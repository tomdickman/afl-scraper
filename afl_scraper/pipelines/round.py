from ..scraper import (
    load_season_manifest,
    scrape_match,
    scrape_match_ids,
    sync_browser_context,
)
from .match import load_match_data


def round_pipeline(
    round_number: str,
    year: int | None = None,
    headless: bool = True,
    load: bool = True,
) -> list[dict]:
    results = []

    with sync_browser_context(headless) as browser:
        ids = scrape_match_ids(browser, round_number, year)
        try:
            manifest = load_season_manifest(year)
        except FileNotFoundError:
            manifest = None
        print(
            f"Found {len(ids)} matches in round {round_number} of {year or 'current'}"
        )

        for match_id in ids:
            print(f"\n--- Match {match_id} ---")
            try:
                raw_data = scrape_match(
                    browser,
                    match_id,
                    expected_year=year,
                    fixture=manifest.fixture_for(match_id) if manifest else None,
                )
                if load:
                    result = load_match_data(raw_data, int(match_id))
                else:
                    result = {"raw_data": raw_data}
                results.append(result)
                print(f"--- Match {match_id} done ---")
            except Exception as e:
                print(f"  Error processing match {match_id}: {e}")
                results.append({"error": str(e)})

    return results
