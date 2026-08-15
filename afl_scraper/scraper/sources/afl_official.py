import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Locator, Page

from ...models.player import PlayerInfo
from .base import PlayerSource


TEAM_SLUGS = {
    "adelaide-crows": "Adelaide Crows",
    "brisbane-lions": "Brisbane Lions",
    "carlton": "Carlton",
    "collingwood": "Collingwood",
    "essendon": "Essendon",
    "fremantle": "Fremantle",
    "geelong-cats": "Geelong Cats",
    "gold-coast-suns": "Gold Coast Suns",
    "gws-giants": "GWS Giants",
    "hawthorn": "Hawthorn",
    "melbourne": "Melbourne",
    "north-melbourne": "North Melbourne",
    "port-adelaide": "Port Adelaide",
    "richmond": "Richmond",
    "st-kilda": "St Kilda",
    "sydney-swans": "Sydney Swans",
    "west-coast-eagles": "West Coast Eagles",
    "western-bulldogs": "Western Bulldogs",
}

PLAYER_CARD_SELECTOR = '[aria-label="Player Card"]'
MIN_PLAYERS_PER_TEAM = 35
MAX_PLAYERS_PER_TEAM = 60
_PLAYER_PATH_PATTERN = re.compile(r"(?:^|/)players/(?P<id>\d+)(?:/|$)")


def _normalized_text(locator: Locator) -> str:
    return " ".join((locator.text_content() or "").split())


class AFLOfficialSource(PlayerSource):
    """Player source implementation for the current AFL team rosters."""

    @property
    def name(self) -> str:
        return "afl_official"

    def get_list_page_url(self, year: int) -> str:
        return "https://www.afl.com.au/teams"

    def get_player_page_url(self, player_id: str) -> str:
        return f"https://www.afl.com.au/players/{player_id}"

    def player_id_from_url(self, url: str) -> str:
        match = _PLAYER_PATH_PATTERN.search(urlparse(url).path)
        if match is None:
            raise RuntimeError(f"Failed to parse player ID from URL: {url}")
        return match.group("id")

    def scrape_player_ids(
        self, page: Page, year: int | None = None
    ) -> list[PlayerInfo]:
        raise NotImplementedError(
            "AFL official requires navigating per-team pages. "
            "Use scrape_player_ids_from_browser instead."
        )

    def _player_from_card(self, card: Locator, team_name: str, year: int) -> PlayerInfo:
        href = card.get_attribute("href")
        if not href:
            raise ValueError(f"AFL player card for {team_name} has no href")

        first_name = _normalized_text(card.locator(".player-grid__player-first-name"))
        last_name = _normalized_text(card.locator(".player-grid__player-surname"))
        if not first_name or not last_name:
            raise ValueError(
                f"AFL player card {href!r} for {team_name} has no complete name"
            )

        return PlayerInfo(
            id=self.player_id_from_url(href),
            first_name=first_name,
            last_name=last_name,
            team=team_name,
            year=year,
        )

    def _scrape_team(self, page: Page, team_name: str, year: int) -> list[PlayerInfo]:
        cards = page.locator(PLAYER_CARD_SELECTOR)
        cards.first.wait_for(state="visible")
        count = cards.count()
        if not MIN_PLAYERS_PER_TEAM <= count <= MAX_PLAYERS_PER_TEAM:
            raise ValueError(
                f"AFL roster for {team_name} has {count} players; expected "
                f"between {MIN_PLAYERS_PER_TEAM} and {MAX_PLAYERS_PER_TEAM}"
            )
        players = [
            self._player_from_card(card, team_name, year) for card in cards.all()
        ]
        ids = [player.id for player in players]
        if len(ids) != len(set(ids)):
            raise ValueError(
                f"AFL roster for {team_name} contains duplicate player IDs"
            )
        return players

    def scrape_player_ids_from_browser(
        self, browser, year: int | None = None
    ) -> list[PlayerInfo]:
        current_year = datetime.now().year
        year = current_year if year is None else year
        if year != current_year:
            raise ValueError(
                "AFL team pages expose only the current roster; refusing to label "
                f"current data as {year}"
            )

        from ..browser import get_team_page

        all_players: list[PlayerInfo] = []
        for team_slug, team_name in TEAM_SLUGS.items():
            page = get_team_page(browser, team_slug)
            try:
                all_players.extend(self._scrape_team(page, team_name, year))
            finally:
                page.close()

        player_teams: dict[str, str] = {}
        for player in all_players:
            previous_team = player_teams.get(player.id)
            if previous_team is not None:
                raise ValueError(
                    f"AFL official player ID {player.id} appeared more than once "
                    f"({previous_team}, {player.team})"
                )
            player_teams[player.id] = player.team

        observed_teams = {player.team for player in all_players}
        expected_teams = set(TEAM_SLUGS.values())
        if observed_teams != expected_teams:
            missing = sorted(expected_teams - observed_teams)
            raise ValueError(f"AFL roster scrape is missing clubs: {missing}")
        return all_players

    def scrape_player(
        self,
        page: Page,
        player_id: str | None = None,
        output_dir: Path | None = None,
    ) -> Path:
        raise NotImplementedError("AFL official scrape_player not yet implemented")
