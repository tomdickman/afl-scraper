"""Resumable AFL Tables player preparation for the 2006-2011 backfill."""

import json
import logging
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from ..models import Player, PlayerInfo
from ..scraper import sync_browser_context
from ..scraper.models.australian_football import MAX_SUPPORTED_YEAR, MIN_SUPPORTED_YEAR
from ..scraper.scrape_player_ids import (
    save_player_id_snapshot_range,
    scrape_player_ids,
)
from ..scraper.sources import PlayerSourceFactory
from ..storage import admin_connection_pool, save_model
from ..transformer.player import transform_player_page
from ..utils.identity import normalize_person_name


SOURCE = "afl_tables"
MAPPING_ROOT = Path("data/mapping")
RAW_ROOT = Path("data/raw/afl_tables")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HistoricalPlayerPreparationReport:
    start_year: int
    end_year: int
    snapshots: int
    unique_players: int
    downloaded_profiles: int
    reused_profiles: int
    dry_run: bool
    inserted_players: int = 0
    updated_players: int = 0


def validate_historical_player_range(start_year: int, end_year: int) -> None:
    if start_year > end_year:
        raise ValueError("Historical player start year must not exceed end year")
    if start_year < MIN_SUPPORTED_YEAR or end_year > MAX_SUPPORTED_YEAR:
        raise ValueError(
            "Historical player preparation supports "
            f"{MIN_SUPPORTED_YEAR}-{MAX_SUPPORTED_YEAR}; got "
            f"{start_year}-{end_year}"
        )


def _snapshot_path(year: int) -> Path:
    return MAPPING_ROOT / f"{year}_{SOURCE}.json"


def _load_snapshot(year: int) -> list[PlayerInfo]:
    path = _snapshot_path(year)
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (json.JSONDecodeError, OSError) as error:
        raise ValueError(f"Invalid AFL Tables snapshot {path}: {error}") from error
    try:
        players = [PlayerInfo.model_validate(item) for item in items]
        PlayerSourceFactory.get(SOURCE).validate_player_snapshot(players, year)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid AFL Tables snapshot {path}: {error}") from error
    return players


def _load_or_find_missing_snapshots(
    years: range, *, refresh: bool, offline: bool
) -> tuple[dict[int, list[PlayerInfo]], list[int]]:
    snapshots = {}
    missing = []
    for year in years:
        if refresh:
            missing.append(year)
            continue
        try:
            snapshots[year] = _load_snapshot(year)
        except FileNotFoundError:
            missing.append(year)
    if missing and offline:
        raise FileNotFoundError(
            "Missing AFL Tables snapshots for years: " + ", ".join(map(str, missing))
        )
    return snapshots, missing


def _fetch_snapshots(
    years: list[int], *, refresh: bool, delay_ms: int, headless: bool, progress=None
) -> dict[int, list[PlayerInfo]]:
    snapshots = {}
    with sync_browser_context(headless) as browser:
        for index, year in enumerate(years):
            if index:
                time.sleep(delay_ms / 1000)
            if progress is not None:
                progress(f"[{year}] scraping AFL Tables player snapshot")
            snapshots[year] = scrape_player_ids(browser, year, SOURCE)
            if not refresh:
                save_player_id_snapshot_range({year: snapshots[year]}, SOURCE)
    if refresh:
        save_player_id_snapshot_range(snapshots, SOURCE)
    return snapshots


def _remove_directory_best_effort(path: Path) -> None:
    try:
        shutil.rmtree(path)
    except OSError as error:
        logger.warning(
            "Could not remove obsolete profile directory %s: %s", path, error
        )


def _profile_path(player_id: str, root: Path | None = None) -> Path:
    root = RAW_ROOT if root is None else root
    return root / "player" / f"{player_id}.html"


def _validate_profile(path: Path, player_id: str) -> Player:
    try:
        player = transform_player_page(path)
    except Exception as error:
        raise ValueError(
            f"Invalid cached AFL Tables profile {path}: {error}"
        ) from error
    if player.id != player_id:
        raise ValueError(
            f"Cached AFL Tables profile {path} produced ID {player.id!r}, "
            f"expected {player_id!r}"
        )
    return player


def _inspect_profiles(
    player_ids: set[str], *, refresh: bool, offline: bool
) -> tuple[dict[str, Player], list[str]]:
    players = {}
    required_downloads = []
    for player_id in sorted(player_ids):
        path = _profile_path(player_id)
        if refresh:
            required_downloads.append(player_id)
            continue
        if not path.exists():
            required_downloads.append(player_id)
            continue
        players[player_id] = _validate_profile(path, player_id)
    if required_downloads and offline:
        raise FileNotFoundError(
            f"Missing AFL Tables profiles for {len(required_downloads)} players; "
            f"first IDs: {', '.join(required_downloads[:10])}"
        )
    return players, required_downloads


def _promote_profile_directory(staging: Path, final: Path) -> None:
    backup = final.with_name(f".player-backup-{uuid4().hex}")
    try:
        if final.exists():
            final.replace(backup)
        staging.replace(final)
    except Exception:
        if not final.exists() and backup.exists():
            backup.replace(final)
        raise
    else:
        if backup.exists():
            _remove_directory_best_effort(backup)


def _scrape_profiles_into(
    browser,
    player_ids: list[str],
    output_dir: Path,
    *,
    delay_ms: int,
    promote_to: Path | None = None,
    progress=None,
) -> None:
    source = PlayerSourceFactory.get(SOURCE)
    page = browser.new_page()
    try:
        total = len(player_ids)
        for index, player_id in enumerate(player_ids, start=1):
            if index > 1:
                time.sleep(delay_ms / 1000)
            url = source.get_player_page_url(player_id)
            response = page.goto(url)
            source.validate_player_navigation(page, response, url)
            staged = source.scrape_player(page, player_id, output_dir=output_dir)
            _validate_profile(staged, player_id)
            if promote_to is not None:
                staged.replace(promote_to / staged.name)
            if progress is not None and (
                index == 1 or index == total or index % 25 == 0
            ):
                progress(f"[{index}/{total}] cached AFL Tables profile {player_id}")
    finally:
        page.close()


def _fetch_profiles(
    player_ids: list[str],
    *,
    refresh: bool,
    delay_ms: int,
    headless: bool,
    progress=None,
) -> None:
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    final = RAW_ROOT / "player"
    staging = Path(tempfile.mkdtemp(prefix=".historical-player-run-", dir=RAW_ROOT))
    try:
        if refresh and final.exists():
            shutil.copytree(final, staging, dirs_exist_ok=True)
        with sync_browser_context(headless) as browser:
            if refresh:
                _scrape_profiles_into(
                    browser,
                    player_ids,
                    staging,
                    delay_ms=delay_ms,
                    progress=progress,
                )
            else:
                final.mkdir(parents=True, exist_ok=True)
                _scrape_profiles_into(
                    browser,
                    player_ids,
                    staging,
                    delay_ms=delay_ms,
                    promote_to=final,
                    progress=progress,
                )

        if refresh:
            for player_id in player_ids:
                _validate_profile(staging / f"{player_id}.html", player_id)
            _promote_profile_directory(staging, final)
    finally:
        if staging.exists():
            _remove_directory_best_effort(staging)


def _validate_cross_year_identities(snapshots: dict[int, list[PlayerInfo]]) -> set[str]:
    names: dict[str, str] = {}
    for year in sorted(snapshots):
        for player in snapshots[year]:
            identity = normalize_person_name(player.display_name())
            previous = names.setdefault(player.id, identity)
            if previous != identity:
                raise ValueError(
                    f"AFL Tables player ID {player.id} changed name across snapshots: "
                    f"{previous!r} vs {identity!r} in {year}"
                )
    return set(names)


def prepare_historical_players(
    start_year: int = MIN_SUPPORTED_YEAR,
    end_year: int = MAX_SUPPORTED_YEAR,
    *,
    load: bool = False,
    refresh: bool = False,
    offline: bool = False,
    headless: bool = True,
    delay_ms: int = 500,
    progress=None,
) -> HistoricalPlayerPreparationReport:
    """Prepare canonical AFL Tables players and year-scoped mapping snapshots."""
    validate_historical_player_range(start_year, end_year)
    if refresh and offline:
        raise ValueError("--refresh and --offline cannot be used together")
    if delay_ms < 0:
        raise ValueError("AFL Tables request delay must not be negative")

    years = range(start_year, end_year + 1)
    snapshots, missing_years = _load_or_find_missing_snapshots(
        years, refresh=refresh, offline=offline
    )
    if missing_years:
        snapshots.update(
            _fetch_snapshots(
                missing_years,
                refresh=refresh,
                delay_ms=delay_ms,
                headless=headless,
                progress=progress,
            )
        )
    player_ids = _validate_cross_year_identities(snapshots)

    players, required_downloads = _inspect_profiles(
        player_ids, refresh=refresh, offline=offline
    )
    if required_downloads:
        _fetch_profiles(
            required_downloads,
            refresh=refresh,
            delay_ms=delay_ms,
            headless=headless,
            progress=progress,
        )
        players = {
            player_id: _validate_profile(_profile_path(player_id), player_id)
            for player_id in sorted(player_ids)
        }
    if set(players) != player_ids:
        raise ValueError("AFL Tables profile preflight did not cover every snapshot ID")

    inserted = 0
    updated = 0
    if load:
        with admin_connection_pool() as connection:
            with connection.transaction():
                for player_id in sorted(players):
                    result = save_model(connection, players[player_id])
                    if result.was_inserted:
                        inserted += 1
                    else:
                        updated += 1

    return HistoricalPlayerPreparationReport(
        start_year=start_year,
        end_year=end_year,
        snapshots=len(snapshots),
        unique_players=len(players),
        downloaded_profiles=len(required_downloads),
        reused_profiles=len(players) - len(required_downloads),
        dry_run=not load,
        inserted_players=inserted,
        updated_players=updated,
    )
