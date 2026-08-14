from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

from ..models.player import PlayerInfo
from .sources import PlayerSourceFactory


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
        page.goto(source_obj.get_list_page_url(year))
        return source_obj.scrape_player_ids(page, year)
    finally:
        page.close()


def save_player_ids_to_json(
    players: list[PlayerInfo], source_name: str, year: int
) -> Path:
    path = Path(f"data/mapping/{year}_{source_name}.json")
    path.parent.mkdir(parents=True, exist_ok=True)

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

    temporary_path: Path | None = None
    try:
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
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    return path
