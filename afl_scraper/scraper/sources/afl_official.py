from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page

from ...models.player import PlayerInfo
from .base import PlayerSource


TEAM_SLUGS = [
    "adelaide-crows", "brisbane", "carlton", "collingwood",
    "essendon", "fremantle", "geelong", "gold-coast",
    "gws-giants", "hawthorn", "melbourne", "north-melbourne",
    "port-adelaide", "richmond", "st-kilda", "sydney-swans",
    "west-coast-eagles", "western-bulldogs",
]


def _team_slug_to_name(slug: str) -> str:
    name = slug.replace("-", " ").title()
    overrides = {
        "Gws Giants": "GWS Giants",
        "West Coast Eagles": "West Coast Eagles",
        "Sydney Swans": "Sydney Swans",
        "North Melbourne": "North Melbourne",
    }
    for key, val in overrides.items():
        name = name.replace(key, val)
    return name


class AFLOfficialSource(PlayerSource):
    """Player source implementation for https://www.afl.com.au."""

    @property
    def name(self) -> str:
        return "afl_official"

    def get_list_page_url(self, year: int) -> str:
        return "https://www.afl.com.au/teams"

    def get_player_page_url(self, player_id: str) -> str:
        return f"https://www.afl.com.au/players/{player_id}"

    def player_id_from_url(self, url: str) -> str:
        parts = url.strip("/").split("/")
        for part in parts:
            if part.isdigit() and len(part) == 4:
                return part
        raise RuntimeError(f"Failed to parse player ID from URL: {url}")

    def scrape_player_ids(self, page: Page, year: int | None = None) -> list[PlayerInfo]:
        raise NotImplementedError(
            "AFL official requires navigating per-team pages. Use scrape_player_ids_from_browser instead."
        )

    def scrape_player_ids_from_browser(self, browser, year: int | None = None) -> list[PlayerInfo]:
        if year is None:
            year = datetime.now().year

        from ..browser import get_team_page

        all_players = []

        for team_slug in TEAM_SLUGS:
            page = get_team_page(browser, team_slug)
            player_links = page.locator('[aria-label="Player Card"]').all()

            for link in player_links:
                href = link.get_attribute("href")
                if not href:
                    continue

                parts = href.strip("/").split("/")
                if len(parts) < 2:
                    continue

                player_id = parts[1]
                name = parts[2] if len(parts) > 2 else ""

                first_name = ""
                last_name = ""
                if name:
                    name_parts = name.split("-")
                    first_name = name_parts[0] if name_parts else ""
                    last_name = "-".join(name_parts[1:]) if len(name_parts) > 1 else ""

                all_players.append(PlayerInfo(
                    id=player_id,
                    first_name=first_name,
                    last_name=last_name,
                    team=_team_slug_to_name(team_slug),
                    year=year,
                ))

        return all_players

    def scrape_player(self, page: Page, player_id: str | None = None) -> Path:
        raise NotImplementedError("AFL official scrape_player not yet implemented")
