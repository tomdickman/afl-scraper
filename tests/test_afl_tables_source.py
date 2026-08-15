from pathlib import Path

import pytest

from afl_scraper.scraper.sources.afl_tables import (
    AFLTablesSource,
    MIN_PLAYERS_PER_TEAM,
)
from afl_scraper.scraper.constants import competition_rules_for_year


class LocatorList:
    def __init__(self, items):
        self.items = items

    @property
    def first(self):
        return self.items[0] if self.items else TextLocator("")

    def all(self):
        return self.items

    def count(self):
        return len(self.items)


class TextLocator:
    def __init__(self, text):
        self.text = text

    def text_content(self):
        return self.text

    def count(self):
        return 1 if self.text else 0


class PlayerLink(TextLocator):
    def __init__(self, player_id, text="Smith, Alex"):
        super().__init__(text)
        self.href = f"players/P/{player_id}.html"

    def get_attribute(self, name):
        return self.href if name == "href" else None


class TeamTable:
    def __init__(self, team, links):
        self.team = team
        self.links = links

    def locator(self, selector):
        if selector == "thead th a":
            return LocatorList([TextLocator(self.team)])
        if selector == 'tbody a[href*="players/"]':
            return LocatorList(self.links)
        raise AssertionError(f"Unexpected selector: {selector}")


class Page:
    def __init__(self, tables=None, body="healthy", url=""):
        self.tables = tables or []
        self.body = body
        self.url = url
        self.html = "<html><h1>Alex Smith</h1><p>1-Jan-2000</p></html>"

    def locator(self, selector):
        if selector == "table":
            return LocatorList(self.tables)
        if selector == "body":
            return TextLocator(self.body)
        if selector == "h1":
            return TextLocator("Alex Smith")
        raise AssertionError(f"Unexpected selector: {selector}")

    def content(self):
        return self.html


class Response:
    def __init__(self, ok=True, status=200):
        self.ok = ok
        self.status = status


def healthy_page(year=2026):
    tables = []
    next_id = 1
    for team in competition_rules_for_year(year).teams:
        links = [
            PlayerLink(f"P{next_id + index}") for index in range(MIN_PLAYERS_PER_TEAM)
        ]
        next_id += MIN_PLAYERS_PER_TEAM
        tables.append(TeamTable(team, links))
    return Page(tables=tables)


def test_current_contract_requires_all_18_complete_unique_teams():
    players = AFLTablesSource().scrape_player_ids(healthy_page(), 2026)
    expected_teams = competition_rules_for_year(2026).teams

    assert len(players) == len(expected_teams) * MIN_PLAYERS_PER_TEAM
    assert {player.team for player in players} == set(expected_teams)
    assert len({player.id for player in players}) == len(players)


def test_missing_team_fails_instead_of_returning_partial_result():
    page = healthy_page()
    page.tables.pop()

    with pytest.raises(ValueError, match="missing teams"):
        AFLTablesSource().scrape_player_ids(page, 2026)


def test_implausibly_small_team_fails_closed():
    page = healthy_page()
    page.tables[0].links.pop()

    with pytest.raises(ValueError, match="has 19 players"):
        AFLTablesSource().scrape_players_links(page, 2026)


def test_duplicate_player_id_across_teams_fails_closed():
    page = healthy_page()
    page.tables[1].links[0] = page.tables[0].links[0]

    with pytest.raises(ValueError, match="appeared more than once"):
        AFLTablesSource().scrape_player_ids(page, 2026)


def test_outage_signature_is_rejected_even_with_http_200():
    page = Page(
        body="Site is down, awaiting solutions.",
        url="https://afltables.com/afl/stats/2026.html",
    )

    with pytest.raises(RuntimeError, match="outage signature"):
        AFLTablesSource().validate_list_navigation(page, Response(), 2026)


def test_http_failure_and_redirect_are_rejected():
    source = AFLTablesSource()
    expected_url = source.get_list_page_url(2026)

    with pytest.raises(RuntimeError, match="HTTP 503"):
        source.validate_list_navigation(
            Page(url=expected_url), Response(False, 503), 2026
        )
    with pytest.raises(RuntimeError, match="unexpected URL"):
        source.validate_list_navigation(
            Page(url="https://afltables.com/maintenance"), Response(), 2026
        )


@pytest.mark.parametrize(
    ("year", "team_count", "historical_name"),
    [(2006, 16, "Kangaroos"), (2008, 16, "North Melbourne"), (2011, 17, "Gold Coast")],
)
def test_historical_competition_eras_are_validated(year, team_count, historical_name):
    page = healthy_page(year)
    page.url = f"https://afltables.com/afl/stats/{year}.html"

    AFLTablesSource().validate_list_navigation(page, Response(), year)
    players = AFLTablesSource().scrape_player_ids(page, year)

    assert len({player.team for player in players}) == team_count
    assert historical_name in {player.team for player in players}


def test_seasons_before_career_history_floor_are_rejected_explicitly():
    with pytest.raises(ValueError, match="configured competition eras from 2006"):
        AFLTablesSource().validate_list_navigation(Page(), Response(), 2005)


def test_player_page_is_validated_before_staging(tmp_path):
    source = AFLTablesSource()
    page = Page(body="Alex Smith 1-Jan-2000")

    path = source.scrape_player(page, "Alex_Smith", output_dir=tmp_path)

    assert path == tmp_path / "Alex_Smith.html"
    assert path.read_text() == page.html

    page.body = "Alex Smith"
    with pytest.raises(ValueError, match="no birthdate"):
        source.scrape_player(page, "Alex_Smith", output_dir=tmp_path)


def test_relative_player_ids_parse_without_url_join():
    source = AFLTablesSource()

    assert source.player_id_from_url("players/J/Jordan_Dawson.html") == "Jordan_Dawson"
    assert (
        source.player_id_from_url(
            "https://afltables.com/afl/stats/players/J/Jordan_Dawson.html"
        )
        == "Jordan_Dawson"
    )
