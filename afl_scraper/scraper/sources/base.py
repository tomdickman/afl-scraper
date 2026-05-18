from abc import ABC, abstractmethod

from playwright.sync_api import Page

from ...models.player import PlayerInfo


class PlayerSource(ABC):
    """Base class for player data source scraping."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this source (e.g. 'afl_tables', 'afl_official')."""

    @abstractmethod
    def get_list_page_url(self, year: int) -> str:
        """Construct the URL for the year listing page."""

    @abstractmethod
    def get_player_page_url(self, player_id: str) -> str:
        """Construct the URL for a single player page."""

    @abstractmethod
    def player_id_from_url(self, url: str) -> str:
        """Extract the player ID segment from a player page URL."""

    @abstractmethod
    def scrape_player_ids(self, page: Page, year: int) -> list[PlayerInfo]:
        """Scrape all player IDs, names, and teams for the given year."""

    @abstractmethod
    def scrape_player(self, page: Page, player_id: str | None = None) -> object:
        """Save raw unstructured player data to the data lake."""

    def scrape_players_links(self, page: Page) -> list[str]:
        """Scrape links to raw player data from the year listing page."""
        raise NotImplementedError(f"{self.name} does not support scrape_players_links")
