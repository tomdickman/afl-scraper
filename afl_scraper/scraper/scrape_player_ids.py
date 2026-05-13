from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page

from .browser import get_team_page


def scrape_afl_official_player_ids(
    browser: BrowserContext, year: int = None
) -> list[dict[str, Any]]:
    if year is None:
        year = datetime.now().year

    teams = [
        "adelaide-crows",
        "brisbane",
        "carlton",
        "collingwood",
        "essendon",
        "fremantle",
        "geelong",
        "gold-coast",
        "gws-giants",
        "hawthorn",
        "melbourne",
        "north-melbourne",
        "port-adelaide",
        "richmond",
        "st-kilda",
        "sydney-swans",
        "west-coast-eagles",
        "western-bulldogs",
    ]

    all_players = []

    for team_slug in teams:
        page = get_team_page(browser, team_slug)
        player_links = page.locator('[aria-label="Player Card"]').all()

        for link in player_links:
            href = link.get_attribute("href")
            if href:
                parts = href.strip("/").split("/")
                if len(parts) >= 2:
                    player_id = parts[1]
                    name = parts[2] if len(parts) > 2 else ""

                    first_name = ""
                    last_name = ""
                    if name:
                        name_parts = name.split("-")
                        first_name = name_parts[0] if name_parts else ""
                        last_name = (
                            "-".join(name_parts[1:]) if len(name_parts) > 1 else ""
                        )

                    team_name = team_slug.replace("-", " ").title()
                    team_name = team_name.replace("Gws Giants", "GWS Giants")
                    team_name = team_name.replace(
                        "West Coast Eagles", "West Coast Eagles"
                    )
                    team_name = team_name.replace("Sydney Swans", "Sydney Swans")
                    team_name = team_name.replace("North Melbourne", "North Melbourne")

                    all_players.append(
                        {
                            "id": player_id,
                            "firstName": first_name,
                            "lastName": last_name,
                            "team": team_name,
                            "year": year,
                        }
                    )

    return all_players


def scrape_afl_tables_player_ids(
    browser: BrowserContext, year: int = None
) -> list[dict[str, Any]]:
    if year is None:
        year = datetime.now().year

    page = browser.new_page()
    page.goto(f"https://afltables.com/afl/stats/{year}.html")

    team_sections = page.locator("table").all()

    all_players = []

    for team_table in team_sections:
        header = team_table.locator("thead tr th").first
        team_name = header.text_content() if header else ""
        team_name = team_name.strip() if team_name else ""

        if not team_name:
            continue

        rows = team_table.locator("tbody tr").all()

        for row in rows:
            player_link = row.locator("td a").first
            href = player_link.get_attribute("href") if player_link else None

            if not href or "/stats/players/" not in href:
                continue

            player_id = href.split("/")[-1].replace(".html", "")

            name_cell = row.locator("td").first
            full_name = name_cell.text_content() if name_cell else ""

            if full_name:
                parts = full_name.strip().split()
                first_name = parts[0] if parts else ""
                last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

                all_players.append(
                    {
                        "id": player_id,
                        "firstName": first_name,
                        "lastName": last_name,
                        "team": team_name,
                        "year": year,
                    }
                )

    return all_players


def save_player_ids_to_json(
    players: list[dict[str, Any]], source: str, year: int
) -> Path:
    path = Path(f"data/mapping/{year}_{source}.json")
    path.parent.mkdir(parents=True, exist_ok=True)

    import json

    with open(path, "w") as f:
        json.dump(players, f, indent=2)

    return path
