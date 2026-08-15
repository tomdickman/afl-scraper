from collections import Counter
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from ..models.player import PlayerInfo
from .sources import PlayerSourceFactory


logger = logging.getLogger(__name__)


def _unlink_best_effort(path: Path) -> None:
    """Remove obsolete snapshot data without changing a completed operation."""
    try:
        path.unlink()
    except OSError as exc:
        logger.warning("Could not remove obsolete snapshot file %s: %s", path, exc)


def scrape_player_ids(
    browser, year: int | None = None, source: str = "afl_tables"
) -> list[PlayerInfo]:
    if year is None:
        year = datetime.now().year

    source_obj = PlayerSourceFactory.get(source)

    if source == "afl_official":
        return source_obj.scrape_player_ids_from_browser(browser, year)

    page = browser.new_page()
    try:
        response = page.goto(source_obj.get_list_page_url(year))
        if source == "afl_tables":
            source_obj.validate_list_navigation(page, response, year)
        return source_obj.scrape_player_ids(page, year)
    finally:
        page.close()


def save_player_ids_to_json(
    players: list[PlayerInfo], source_name: str, year: int
) -> Path:
    return save_player_id_snapshots({source_name: players}, year)[source_name]


def _validate_snapshot(players: list[PlayerInfo], source_name: str, year: int) -> None:
    if not players:
        raise ValueError(f"Refusing to save empty {source_name} player snapshot")
    wrong_year = sorted({player.year for player in players if player.year != year})
    if wrong_year:
        raise ValueError(
            f"Refusing to save {source_name} snapshot for {year}; "
            f"records contain years {wrong_year}"
        )
    ids = [player.id for player in players]
    duplicates = sorted(
        player_id for player_id, count in Counter(ids).items() if count > 1
    )
    if duplicates:
        raise ValueError(
            f"Refusing to save {source_name} snapshot with duplicate IDs: "
            f"{', '.join(duplicates)}"
        )


def _write_temporary_snapshot(players: list[PlayerInfo], path: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)
        json.dump(
            [player.model_dump(by_alias=True) for player in players],
            temporary_file,
            indent=2,
        )
        temporary_file.flush()
        os.fsync(temporary_file.fileno())
    return temporary_path


def save_player_id_snapshots(
    snapshots: dict[str, list[PlayerInfo]], year: int
) -> dict[str, Path]:
    """Validate every source before promoting any year-scoped snapshot."""
    if not snapshots:
        raise ValueError("No player ID snapshots supplied")
    for source_name, players in snapshots.items():
        _validate_snapshot(players, source_name, year)

    mapping_dir = Path("data/mapping")
    mapping_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        source_name: mapping_dir / f"{year}_{source_name}.json"
        for source_name in snapshots
    }
    temporary_paths: dict[str, Path] = {}
    backup_paths: dict[str, Path] = {}
    promoted: list[str] = []
    try:
        for source_name, players in snapshots.items():
            temporary_paths[source_name] = _write_temporary_snapshot(
                players, paths[source_name]
            )
        for source_name, path in paths.items():
            if path.exists():
                backup = path.with_name(f".{path.name}.{uuid4().hex}.backup")
                path.replace(backup)
                backup_paths[source_name] = backup
            temporary_paths[source_name].replace(path)
            promoted.append(source_name)
    except Exception:
        for source_name in promoted:
            path = paths[source_name]
            if path.exists():
                path.unlink()
        for source_name, backup in backup_paths.items():
            if backup.exists():
                backup.replace(paths[source_name])
        raise
    finally:
        for temporary_path in temporary_paths.values():
            if temporary_path.exists():
                _unlink_best_effort(temporary_path)

    for backup in backup_paths.values():
        if backup.exists():
            _unlink_best_effort(backup)
    return paths
