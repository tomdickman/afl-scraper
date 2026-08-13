import re
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page

from ...models.player import PlayerInfo
from .base import PlayerSource


class AFLTablesSource(PlayerSource):
    """Player source implementation for https://afltables.com."""

    @property
    def name(self) -> str:
        return "afl_tables"

    def get_list_page_url(self, year: int) -> str:
        return f"https://afltables.com/afl/stats/{year}.html"

    def get_player_page_url(self, player_id: str) -> str:
        initial = player_id[0].upper()
        return f"https://afltables.com/afl/stats/players/{initial}/{player_id}.html"

    def player_id_from_url(self, url: str) -> str:
        pattern = r"/players/[A-Za-z]/([A-Za-z_-]+[0-9]*)\.html$"
        match = re.search(pattern, url)
        if match:
            return match.group(1)
        raise RuntimeError(f"Failed to parse player ID from URL: {url}")

    def scrape_player_ids(
        self, page: Page, year: int | None = None
    ) -> list[PlayerInfo]:
        if year is None:
            year = datetime.now().year

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

            player_links = table.locator('tbody a[href*="players/"]').all()

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

                all_players.append(
                    PlayerInfo(
                        id=player_id,
                        first_name=first_name,
                        last_name=last_name,
                        team=team_name,
                        year=year,
                    )
                )

        return all_players

    def scrape_player(self, page: Page, player_id: str | None = None) -> Path:
        if player_id is None:
            player_id = self.player_id_from_url(page.url)

        path = self.get_raw_data_dir() / "player" / f"{player_id}.html"
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            f.write(page.content())

        if not path.exists():
            raise FileNotFoundError(f"Failed to create file at {path}")

        if path.stat().st_size == 0:
            raise ValueError(f"File created at {path} is empty")

        return path

    def scrape_players_links(self, page: Page) -> list[str]:
        """Scrape links to raw player data from the year stats page."""
        table_links = page.locator("table tbody tr td a").all()
        hrefs = [link.get_attribute("href") for link in table_links]
        return list(dict.fromkeys(h for h in hrefs if h and "players/" in h))
