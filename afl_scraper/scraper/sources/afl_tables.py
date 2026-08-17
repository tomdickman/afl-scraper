import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Locator, Page, Response

from ...models.player import PlayerInfo
from ...diagnostics import summarize_identifiers
from ..constants import MIN_HISTORY_YEAR, competition_rules_for_year
from .base import PlayerSource

MIN_PLAYERS_PER_TEAM = 20
MAX_PLAYERS_PER_TEAM = 60
MIN_SUPPORTED_YEAR = MIN_HISTORY_YEAR
OUTAGE_SIGNATURES = ("site is down", "awaiting solutions")
_BIRTHDATE_PATTERN = re.compile(r"\d{1,2}-[A-Za-z]{3}-\d{4}")


def _text(locator) -> str:
    return " ".join((locator.text_content() or "").split())


class AFLTablesSource(PlayerSource):
    """Validated player source implementation for https://afltables.com."""

    @property
    def name(self) -> str:
        return "afl_tables"

    def get_list_page_url(self, year: int) -> str:
        return f"https://afltables.com/afl/stats/{year}.html"

    def get_player_page_url(self, player_id: str) -> str:
        initial = player_id[0].upper()
        return f"https://afltables.com/afl/stats/players/{initial}/{player_id}.html"

    def player_id_from_url(self, url: str) -> str:
        pattern = r"(?:^|/)players/[A-Za-z]/([A-Za-z_-]+[0-9]*)\.html$"
        match = re.search(pattern, url)
        if match:
            return match.group(1)
        raise RuntimeError(f"Failed to parse player ID from URL: {url}")

    def validate_list_navigation(
        self, page: Page, response: Response | None, year: int
    ) -> None:
        if year < MIN_SUPPORTED_YEAR:
            raise ValueError(
                f"AFL Tables validation supports configured competition eras from "
                f"{MIN_SUPPORTED_YEAR}; got {year}"
            )
        competition_rules_for_year(year)
        expected_url = self.get_list_page_url(year)
        if response is None or not response.ok:
            status = response.status if response is not None else "no response"
            raise RuntimeError(f"AFL Tables season page returned HTTP {status}")
        if page.url.rstrip("/") != expected_url:
            raise RuntimeError(
                f"AFL Tables season page navigated to unexpected URL {page.url!r}"
            )
        body = _text(page.locator("body")).casefold()
        signature = next((value for value in OUTAGE_SIGNATURES if value in body), None)
        if signature:
            raise RuntimeError(
                f"AFL Tables season page contains outage signature {signature!r}"
            )

    def validate_player_navigation(
        self, page: Page, response: Response | None, expected_url: str
    ) -> None:
        if response is None or not response.ok:
            status = response.status if response is not None else "no response"
            raise RuntimeError(f"AFL Tables player page returned HTTP {status}")
        if page.url.rstrip("/") != expected_url:
            raise RuntimeError(
                f"AFL Tables player page navigated to unexpected URL {page.url!r}"
            )

    def _team_tables(self, page: Page, year: int) -> dict[str, Locator]:
        expected_teams = competition_rules_for_year(year).teams
        team_tables = {}
        for table in page.locator("table").all():
            team_links = table.locator("thead th a")
            if team_links.count() == 0:
                continue
            team_name = _text(team_links.first)
            if team_name not in expected_teams:
                raise ValueError(f"Unexpected AFL Tables team section: {team_name!r}")
            if team_name in team_tables:
                raise ValueError(f"Duplicate AFL Tables team section: {team_name}")
            team_tables[team_name] = table

        missing = sorted(set(expected_teams) - set(team_tables))
        if missing:
            raise ValueError(f"AFL Tables season page is missing teams: {missing}")
        return team_tables

    def _validated_team_links(self, page: Page, year: int) -> dict[str, list[Locator]]:
        links_by_team = {}
        observed_ids: dict[str, str] = {}
        for team_name, table in self._team_tables(page, year).items():
            links = table.locator('tbody a[href*="players/"]').all()
            if not MIN_PLAYERS_PER_TEAM <= len(links) <= MAX_PLAYERS_PER_TEAM:
                raise ValueError(
                    f"AFL Tables roster for {team_name} has {len(links)} players; "
                    f"expected between {MIN_PLAYERS_PER_TEAM} and "
                    f"{MAX_PLAYERS_PER_TEAM}"
                )
            for link in links:
                href = link.get_attribute("href")
                if not href:
                    raise ValueError(
                        f"AFL Tables player link for {team_name} has no href"
                    )
                player_id = self.player_id_from_url(href)
                previous_team = observed_ids.get(player_id)
                if previous_team is not None:
                    raise ValueError(
                        f"AFL Tables player ID {player_id} appeared more than once "
                        f"({previous_team}, {team_name})"
                    )
                observed_ids[player_id] = team_name
            links_by_team[team_name] = links
        return links_by_team

    def scrape_player_ids(
        self, page: Page, year: int | None = None
    ) -> list[PlayerInfo]:
        year = datetime.now().year if year is None else year
        players = []
        for team_name, links in self._validated_team_links(page, year).items():
            for link in links:
                href = link.get_attribute("href")
                player_id = self.player_id_from_url(href)
                name_text = _text(link)
                parts = name_text.split(", ")
                if len(parts) == 2:
                    last_name, first_name = (part.strip() for part in parts)
                else:
                    name_parts = name_text.split()
                    first_name = name_parts[0] if name_parts else ""
                    last_name = " ".join(name_parts[1:])
                if not first_name or not last_name:
                    raise ValueError(
                        f"AFL Tables player {player_id} has incomplete name {name_text!r}"
                    )
                players.append(
                    PlayerInfo(
                        id=player_id,
                        first_name=first_name,
                        last_name=last_name,
                        team=team_name,
                        year=year,
                    )
                )
        self.validate_player_snapshot(players, year)
        return players

    def validate_player_snapshot(self, players: list[PlayerInfo], year: int) -> None:
        """Revalidate a cached AFL Tables season snapshot without the website."""
        expected_teams = set(competition_rules_for_year(year).teams)
        observed_teams = {player.team for player in players}
        if observed_teams != expected_teams:
            missing = sorted(expected_teams - observed_teams)
            unexpected = sorted(observed_teams - expected_teams)
            raise ValueError(
                f"AFL Tables snapshot for {year} has wrong clubs; "
                f"missing={missing}, unexpected={unexpected}"
            )

        wrong_year = sorted({player.year for player in players if player.year != year})
        if wrong_year:
            raise ValueError(
                f"AFL Tables snapshot for {year} contains years {wrong_year}"
            )

        ids = [player.id for player in players]
        duplicates = sorted(
            player_id for player_id, count in Counter(ids).items() if count > 1
        )
        if duplicates:
            raise ValueError(
                f"AFL Tables snapshot contains {len(duplicates)} duplicate player "
                f"IDs: {summarize_identifiers(duplicates)}"
            )

        counts = Counter(player.team for player in players)
        invalid_counts = {
            team: count
            for team, count in sorted(counts.items())
            if not MIN_PLAYERS_PER_TEAM <= count <= MAX_PLAYERS_PER_TEAM
        }
        if invalid_counts:
            raise ValueError(
                f"AFL Tables snapshot for {year} has implausible club counts: "
                f"{invalid_counts}"
            )

        incomplete = sorted(
            player.id
            for player in players
            if not player.first_name.strip() or not player.last_name.strip()
        )
        if incomplete:
            raise ValueError(
                f"AFL Tables snapshot contains {len(incomplete)} incomplete names: "
                f"{summarize_identifiers(incomplete)}"
            )

    def scrape_player(
        self,
        page: Page,
        player_id: str | None = None,
        output_dir: Path | None = None,
    ) -> Path:
        if player_id is None:
            player_id = self.player_id_from_url(page.url)

        heading = page.locator("h1")
        body = _text(page.locator("body"))
        if heading.count() != 1 or not _text(heading):
            raise ValueError(f"AFL Tables player {player_id} has no name heading")
        if _BIRTHDATE_PATTERN.search(body) is None:
            raise ValueError(f"AFL Tables player {player_id} has no birthdate")

        player_dir = output_dir or (self.get_raw_data_dir() / "player")
        path = player_dir / f"{player_id}.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        content = page.content()
        if not content.strip():
            raise ValueError(f"Raw player page for {player_id} is empty")
        path.write_text(content, encoding="utf-8")
        return path

    def scrape_players_links(self, page: Page, year: int | None = None) -> list[str]:
        """Return unique links after validating the season's club sections."""
        year = datetime.now().year if year is None else year
        hrefs = []
        for links in self._validated_team_links(page, year).values():
            hrefs.extend(link.get_attribute("href") for link in links)
        return list(dict.fromkeys(hrefs))
