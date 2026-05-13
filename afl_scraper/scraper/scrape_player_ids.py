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

    tables = page.locator("table").all()

    all_players = []

    for table in tables:
        thead = table.locator("thead").all()
        if not thead:
            continue

        team_link = table.locator("thead th a").first
        team_name = team_link.text_content().strip() if team_link else ""

        if not team_name:
            continue

        player_links = table.locator("tbody a[href*=\"players/\"]").all()

        for link in player_links:
            href = link.get_attribute("href")
            player_id = href.split("/")[-1].replace(".html", "")

            name_text = link.text_content().strip()
            parts = name_text.split(", ")
            if len(parts) == 2:
                last_name = parts[0].strip()
                first_name = parts[1].strip()
            else:
                name_parts = name_text.split()
                first_name = name_parts[0] if name_parts else ""
                last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

            all_players.append({
                "id": player_id,
                "firstName": first_name,
                "lastName": last_name,
                "team": team_name,
                "year": year,
            })

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
