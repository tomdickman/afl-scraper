import logging
from pathlib import Path
import shutil
import tempfile
from typing import List
from urllib.parse import urljoin
from uuid import uuid4

from playwright.sync_api import BrowserContext

from .constants import FIXTURE_CLASSNAMES, PATHS
from .fixture import navigate_to_round, get_fixture_page
from .parser import (
    display_player_stats,
    extract_table_data,
    select_team_stats,
)
from .sources import PlayerSourceFactory


logger = logging.getLogger(__name__)


def _remove_directory_best_effort(path: Path) -> None:
    """Remove obsolete scrape data without changing the scrape outcome."""
    try:
        shutil.rmtree(path)
    except OSError as exc:
        logger.warning("Could not remove obsolete scrape directory %s: %s", path, exc)


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
        matches_locator = page.locator(
            f'{FIXTURE_CLASSNAMES["MATCHES"]}[data-match-id]'
        )
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

        raw_dir = Path("data/raw/afl_official/match") / str(match_id)

        select_team_stats(page, 1)
        _save_raw_html(raw_dir / "home_player_stats.html", page.content())

        select_team_stats(page, 2)
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
    staging_dir: Path | None = None
    try:
        try:
            response = page.goto(list_url)
            if source == "afl_tables":
                source_obj.validate_list_navigation(page, response, year)
            links = source_obj.scrape_players_links(page)
            player_ids = list(
                dict.fromkeys(
                    source_obj.player_id_from_url(urljoin(list_url, link))
                    for link in links
                )
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to scrape {source} player list for {year} "
                f"({list_url}): {exc}"
            ) from exc

        if source == "afl_tables":
            raw_root = source_obj.get_raw_data_dir()
            raw_root.mkdir(parents=True, exist_ok=True)
            staging_dir = Path(tempfile.mkdtemp(prefix=".player-run-", dir=raw_root))

        players_data_paths = []

        for player_id in player_ids:
            player_url = source_obj.get_player_page_url(player_id)
            try:
                response = page.goto(player_url)
                if source == "afl_tables":
                    source_obj.validate_player_navigation(page, response, player_url)
                    player_data_path = source_obj.scrape_player(
                        page, player_id, output_dir=staging_dir
                    )
                else:
                    player_data_path = source_obj.scrape_player(page, player_id)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to scrape {source} player {player_id!r} "
                    f"({player_url}): {exc}"
                ) from exc
            if player_data_path is not None:
                players_data_paths.append(player_data_path)

        if source == "afl_tables":
            if len(players_data_paths) != len(player_ids):
                raise RuntimeError(
                    f"AFL Tables saved {len(players_data_paths)} of "
                    f"{len(player_ids)} player pages"
                )
            final_dir = source_obj.get_raw_data_dir() / "player"
            backup_dir = final_dir.with_name(f".player-backup-{uuid4().hex}")
            try:
                if final_dir.exists():
                    final_dir.replace(backup_dir)
                staging_dir.replace(final_dir)
                staging_dir = None
            except Exception:
                if not final_dir.exists() and backup_dir.exists():
                    backup_dir.replace(final_dir)
                raise
            else:
                if backup_dir.exists():
                    _remove_directory_best_effort(backup_dir)
            players_data_paths = [final_dir / path.name for path in players_data_paths]

        return players_data_paths
    finally:
        if staging_dir is not None and staging_dir.exists():
            _remove_directory_best_effort(staging_dir)
        page.close()
