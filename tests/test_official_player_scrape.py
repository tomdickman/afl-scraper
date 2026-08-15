from datetime import datetime

import pytest

from afl_scraper.models.player import PlayerInfo
from afl_scraper.scraper import browser as browser_helpers
from afl_scraper.scraper.scrape_player_ids import save_player_ids_to_json
from afl_scraper.scraper.sources.afl_official import (
    AFLOfficialSource,
    MAX_PLAYERS_PER_TEAM,
    MIN_PLAYERS_PER_TEAM,
    PLAYER_CARD_SELECTOR,
    TEAM_SLUGS,
)


class TextLocator:
    def __init__(self, text):
        self.text = text

    def text_content(self):
        return self.text


class Card:
    def __init__(self, player_id, first_name="Reilly", last_name="O’Brien"):
        self.href = f"/players/{player_id}/example-player"
        self.first_name = first_name
        self.last_name = last_name

    def get_attribute(self, name):
        return self.href if name == "href" else None

    def locator(self, selector):
        if selector == ".player-grid__player-first-name":
            return TextLocator(self.first_name)
        if selector == ".player-grid__player-surname":
            return TextLocator(self.last_name)
        raise AssertionError(f"Unexpected selector: {selector}")


class Cards:
    def __init__(self, cards):
        self.cards = cards
        self.waited = False

    @property
    def first(self):
        return self

    def wait_for(self, *, state):
        assert state == "visible"
        self.waited = True

    def count(self):
        return len(self.cards)

    def all(self):
        return self.cards


class TeamPage:
    def __init__(self, cards):
        self.cards = Cards(cards)
        self.closed = False

    def locator(self, selector):
        assert selector == PLAYER_CARD_SELECTOR
        return self.cards

    def close(self):
        self.closed = True


def player(player_id="101", year=2026):
    return PlayerInfo(
        id=player_id,
        first_name="Alex",
        last_name="Smith",
        team="Carlton",
        year=year,
    )


def test_official_team_routes_cover_all_clubs_with_correct_slugs():
    assert len(TEAM_SLUGS) == 18
    assert TEAM_SLUGS["brisbane-lions"] == "Brisbane Lions"
    assert TEAM_SLUGS["geelong-cats"] == "Geelong Cats"
    assert TEAM_SLUGS["gold-coast-suns"] == "Gold Coast Suns"
    assert "brisbane" not in TEAM_SLUGS
    assert "geelong" not in TEAM_SLUGS
    assert "gold-coast" not in TEAM_SLUGS


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("/players/35/example", "35"),
        ("https://www.afl.com.au/players/857/example", "857"),
        ("/players/11960/example", "11960"),
    ],
)
def test_official_player_id_has_no_fixed_length_assumption(url, expected):
    assert AFLOfficialSource().player_id_from_url(url) == expected


def test_player_identity_comes_from_semantic_card_fields():
    source = AFLOfficialSource()

    result = source._player_from_card(Card("101"), "Adelaide Crows", 2026)

    assert result.id == "101"
    assert result.first_name == "Reilly"
    assert result.last_name == "O’Brien"
    assert result.team == "Adelaide Crows"


@pytest.mark.parametrize("count", [MIN_PLAYERS_PER_TEAM - 1, MAX_PLAYERS_PER_TEAM + 1])
def test_implausible_team_roster_size_fails_closed(count):
    page = TeamPage([Card(str(index)) for index in range(count)])

    with pytest.raises(ValueError, match=f"has {count} players"):
        AFLOfficialSource()._scrape_team(page, "Carlton", 2026)


def test_duplicate_id_within_team_roster_fails_closed():
    cards = [Card(str(index)) for index in range(MIN_PLAYERS_PER_TEAM)]
    cards[-1] = Card("0")

    with pytest.raises(ValueError, match="duplicate player IDs"):
        AFLOfficialSource()._scrape_team(TeamPage(cards), "Carlton", 2026)


def test_historical_year_is_rejected_before_opening_pages():
    current_year = datetime.now().year

    with pytest.raises(ValueError, match="only the current roster"):
        AFLOfficialSource().scrape_player_ids_from_browser(object(), current_year - 1)


def test_complete_scrape_visits_and_closes_all_18_clubs(monkeypatch):
    current_year = datetime.now().year
    pages = {}
    next_id = 1
    for slug in TEAM_SLUGS:
        cards = [
            Card(str(next_id + index), first_name="Player", last_name=str(index))
            for index in range(MIN_PLAYERS_PER_TEAM)
        ]
        next_id += MIN_PLAYERS_PER_TEAM
        pages[slug] = TeamPage(cards)

    monkeypatch.setattr(
        browser_helpers,
        "get_team_page",
        lambda _browser, slug: pages[slug],
    )

    players = AFLOfficialSource().scrape_player_ids_from_browser(object(), current_year)

    assert len(players) == len(TEAM_SLUGS) * MIN_PLAYERS_PER_TEAM
    assert {item.team for item in players} == set(TEAM_SLUGS.values())
    assert all(page.closed for page in pages.values())


def test_duplicate_official_id_across_rosters_is_rejected(monkeypatch):
    current_year = datetime.now().year
    pages = {}
    for slug in TEAM_SLUGS:
        cards = [Card(str(index)) for index in range(MIN_PLAYERS_PER_TEAM)]
        pages[slug] = TeamPage(cards)
    monkeypatch.setattr(
        browser_helpers,
        "get_team_page",
        lambda _browser, slug: pages[slug],
    )

    with pytest.raises(ValueError, match="appeared more than once"):
        AFLOfficialSource().scrape_player_ids_from_browser(object(), current_year)


def test_snapshot_validation_preserves_last_known_good_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    path = save_player_ids_to_json([player()], "afl_official", 2026)
    original = path.read_text()

    with pytest.raises(ValueError, match="empty"):
        save_player_ids_to_json([], "afl_official", 2026)
    with pytest.raises(ValueError, match="duplicate IDs"):
        save_player_ids_to_json([player(), player()], "afl_official", 2026)
    with pytest.raises(ValueError, match="records contain years"):
        save_player_ids_to_json([player(year=2025)], "afl_official", 2026)

    assert path.read_text() == original
    assert not list(path.parent.glob("*.tmp"))


class Response:
    def __init__(self, ok, status):
        self.ok = ok
        self.status = status


class NavigationPage:
    def __init__(self, response, final_url):
        self.response = response
        self.url = final_url
        self.closed = False

    def goto(self, _url):
        return self.response

    def close(self):
        self.closed = True


class Browser:
    def __init__(self, page):
        self.page = page

    def new_page(self):
        return self.page


def test_team_page_rejects_http_failure_and_closes_page():
    page = NavigationPage(Response(False, 404), "https://www.afl.com.au/404")

    with pytest.raises(RuntimeError, match="HTTP 404"):
        browser_helpers.get_team_page(Browser(page), "missing-club")

    assert page.closed is True


def test_team_page_rejects_unexpected_redirect_and_closes_page():
    page = NavigationPage(Response(True, 200), "https://www.afl.com.au/teams")

    with pytest.raises(RuntimeError, match="unexpected URL"):
        browser_helpers.get_team_page(Browser(page), "brisbane-lions")

    assert page.closed is True


def test_team_page_accepts_exact_successful_url():
    url = "https://www.afl.com.au/teams/brisbane-lions"
    page = NavigationPage(Response(True, 200), url)

    assert browser_helpers.get_team_page(Browser(page), "brisbane-lions") is page
    assert page.closed is False
