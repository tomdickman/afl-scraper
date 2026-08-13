from pathlib import Path
from typing import List

from playwright.sync_api import BrowserContext

from .constants import FIXTURE_CLASSNAMES, PATHS
from .fixture import navigate_to_round, get_fixture_page
from .parser import (
    display_player_stats,
    extract_table_data,
)
from .sources import PlayerSourceFactory


def _normalise_match_id(match_id: int | str) -> int:
    """Return a validated numeric AFL match ID."""
    try:
        normalised = int(match_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid AFL match ID: {match_id!r}") from exc

    if normalised <= 0 or str(match_id).strip() != str(normalised):
        raise ValueError(f"Invalid AFL match ID: {match_id!r}")

    return normalised


def _save_raw_html(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    if path.stat().st_size == 0:
        raise ValueError(f"Raw page was empty: {path}")


def scrape_match_ids(
    browser: BrowserContext, round_number: str, year: int | None = None
) -> list[int]:
    page = get_fixture_page(browser, year)
    try:
        navigate_to_round(page, str(round_number))
        matches_locator = page.locator(FIXTURE_CLASSNAMES["MATCHES"])
        raw_ids = [
            match_locator.get_attribute("data-match-id")
            for match_locator in matches_locator.all()
        ]
        if not raw_ids:
            raise RuntimeError(f"No matches found for round {round_number!r}")
        return [_normalise_match_id(match_id) for match_id in raw_ids]
    finally:
        page.close()


def scrape_match(browser: BrowserContext, match_id: int | str):
    match_id = _normalise_match_id(match_id)
    page = browser.new_page()
    url = f"{PATHS['MATCH'].rstrip('/')}/{match_id}"
    try:
        page.goto(url)
        display_player_stats(page)

        team_selector = page.locator("button#teams-dropdown-button")
        team_options = page.locator(".select__options-wrapper")
        raw_dir = Path("data/raw/afl_official/match") / str(match_id)

        team_selector.click()
        team_options.locator("li:nth-child(2)").click()
        _save_raw_html(raw_dir / "home_player_stats.html", page.content())

        team_selector.click()
        team_options.locator("li:nth-child(3)").click()
        _save_raw_html(raw_dir / "away_player_stats.html", page.content())

        return extract_table_data(page)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to scrape AFL match {match_id} ({url}): {exc}"
        ) from exc
    finally:
        page.close()


def scrape_players(
    browser: BrowserContext, year: int, source: str = "afl_tables"
) -> List[Path]:
    source_obj = PlayerSourceFactory.get(source)
    page = browser.new_page()
    list_url = source_obj.get_list_page_url(year)
    try:
        try:
            page.goto(list_url)
            links = source_obj.scrape_players_links(page)
            player_ids = list(
                dict.fromkeys(source_obj.player_id_from_url(link) for link in links)
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to scrape {source} player list for {year} "
                f"({list_url}): {exc}"
            ) from exc

        players_data_paths = []

        for player_id in player_ids:
            player_url = source_obj.get_player_page_url(player_id)
            try:
                page.goto(player_url)
                player_data_path = source_obj.scrape_player(page, player_id)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to scrape {source} player {player_id!r} "
                    f"({player_url}): {exc}"
                ) from exc
            if player_data_path is not None:
                print(f"Player path scraped: {player_data_path}")
                players_data_paths.append(player_data_path)

        return players_data_paths
    finally:
        page.close()
