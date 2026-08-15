import logging
from datetime import datetime, timezone
from pathlib import Path
import shutil
import tempfile
from typing import List
from urllib.parse import urljoin
from uuid import uuid4

from playwright.sync_api import BrowserContext

from .constants import FIXTURE_CLASSNAMES, PATHS, official_season_id
from .fixture import (
    get_fixture_page,
    get_fixture_url,
    get_round_buttons,
    navigate_to_round,
)
from .models import CachedRawMatch, DiscoveredRound, RawMatchData, SeasonManifest
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


def discover_official_season(browser: BrowserContext, year: int) -> SeasonManifest:
    """Discover and validate every round and match ID in an AFL season."""
    page = get_fixture_page(browser, year)
    try:
        round_labels = list(get_round_buttons(page))
        if not round_labels:
            raise RuntimeError(f"No rounds found for AFL season {year}")

        rounds = []
        for label in round_labels:
            navigate_to_round(page, label)
            matches = page.locator(f'{FIXTURE_CLASSNAMES["MATCHES"]}[data-match-id]')
            match_ids = [
                _normalise_match_id(match.get_attribute("data-match-id"))
                for match in matches.all()
            ]
            if not match_ids:
                raise RuntimeError(
                    f"No matches found for round {label!r} in AFL season {year}"
                )
            rounds.append(DiscoveredRound(label=label, match_ids=match_ids))

        return SeasonManifest(
            year=year,
            season_id=official_season_id(year),
            fixture_url=get_fixture_url(year),
            discovered_at=datetime.now(timezone.utc),
            rounds=rounds,
        )
    finally:
        page.close()


def save_season_manifest(
    manifest: SeasonManifest,
    output_root: Path = Path("data/raw/afl_official/season"),
) -> Path:
    """Atomically save a year-scoped, validated season manifest."""
    output_dir = output_root / str(manifest.year)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "manifest.json"
    temporary_path = output_dir / f".manifest-{uuid4().hex}.tmp"
    try:
        temporary_path.write_text(
            manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return path


def load_season_manifest(
    year: int,
    input_root: Path = Path("data/raw/afl_official/season"),
) -> SeasonManifest:
    """Load and revalidate a previously discovered official season."""
    path = input_root / str(year) / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Season manifest not found: {path}. Run `scrape season {year}` first."
        )
    manifest = SeasonManifest.model_validate_json(path.read_text(encoding="utf-8"))
    if manifest.year != year:
        raise ValueError(
            f"Season manifest at {path} contains year {manifest.year}, expected {year}"
        )
    return manifest


def raw_match_data_path(
    match_id: int | str,
    raw_root: Path = Path("data/raw/afl_official/match"),
) -> Path:
    """Return the canonical validated JSON path for an official match."""
    return raw_root / str(_normalise_match_id(match_id)) / "match.json"


def save_raw_match_data(
    raw_data: RawMatchData,
    match_id: int | str,
    raw_root: Path = Path("data/raw/afl_official/match"),
) -> Path:
    """Atomically persist one fully validated raw match for safe reuse."""
    raw_match = RawMatchData.model_validate(raw_data)
    normalized_match_id = _normalise_match_id(match_id)
    path = raw_match_data_path(normalized_match_id, raw_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.parent / f".match-{uuid4().hex}.tmp"
    cached_match = CachedRawMatch(
        match_id=normalized_match_id,
        source_url=f"{PATHS['MATCH'].rstrip('/')}/{normalized_match_id}",
        scraped_at=datetime.now(timezone.utc),
        data=raw_match,
    )
    try:
        temporary_path.write_text(
            cached_match.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return path


def load_raw_match_data(
    match_id: int | str,
    raw_root: Path = Path("data/raw/afl_official/match"),
) -> RawMatchData:
    """Load and revalidate a cached official match."""
    normalized_match_id = _normalise_match_id(match_id)
    path = raw_match_data_path(normalized_match_id, raw_root)
    if not path.exists():
        raise FileNotFoundError(f"Validated raw match not found: {path}")
    cached_match = CachedRawMatch.model_validate_json(path.read_text(encoding="utf-8"))
    if cached_match.match_id != normalized_match_id:
        raise ValueError(
            f"Raw match cache at {path} contains match {cached_match.match_id}, "
            f"expected {normalized_match_id}"
        )
    return cached_match.data


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

        raw_data = extract_table_data(page)
        save_raw_match_data(raw_data, match_id)
        return raw_data
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
            links = source_obj.scrape_players_links(page, year)
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
