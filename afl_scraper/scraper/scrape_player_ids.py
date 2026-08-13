from datetime import datetime
from pathlib import Path

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
    import json

    path = Path(f"data/mapping/{year}_{source_name}.json")
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(
            [p.model_dump(by_alias=True) for p in players],
            f,
            indent=2,
        )

    return path
