from pathlib import Path

import pytest

from afl_scraper.scraper import browser as browser_helpers
from afl_scraper.scraper import fixture, scrape
from afl_scraper.scraper.sources.afl_tables import AFLTablesSource


class FakeLocator:
    def __init__(self, *, attributes=None, items=None, text=""):
        self.attributes = attributes or {}
        self.items = items or []
        self.text = text
        self.clicked = 0
        self.waited_for = None
        self.children = {}

    @property
    def first(self):
        return self.items[0] if self.items else self

    def all(self):
        return self.items

    def click(self):
        self.clicked += 1

    def get_attribute(self, name):
        return self.attributes.get(name)

    def inner_text(self):
        return self.text

    def locator(self, selector):
        return self.children.setdefault(selector, FakeLocator())

    def wait_for(self, *, state):
        self.waited_for = state


class FakePage:
    def __init__(self):
        self.closed = False
        self.gotos = []
        self.locators = {}
        self.html = "<html>raw fixture</html>"

    def goto(self, url):
        self.gotos.append(url)

    def locator(self, selector):
        return self.locators.setdefault(selector, FakeLocator())

    def content(self):
        return self.html

    def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self, page=None):
        self.page = page or FakePage()
        self.new_page_calls = 0

    def new_page(self):
        self.new_page_calls += 1
        return self.page


def test_navigate_to_round_waits_for_visible_match(monkeypatch):
    page = FakePage()
    button = FakeLocator()
    match = FakeLocator(attributes={"data-match-id": "123"})
    page.locators[f'{fixture.FIXTURE_CLASSNAMES["MATCHES"]}[data-match-id]'] = (
        FakeLocator(items=[match])
    )
    monkeypatch.setattr(fixture, "get_round_buttons", lambda _page: {"4": button})

    assert fixture.navigate_to_round(page, 4) is page

    assert button.clicked == 1
    assert match.waited_for == "visible"


def test_navigate_to_round_reports_available_rounds(monkeypatch):
    monkeypatch.setattr(
        fixture,
        "get_round_buttons",
        lambda _page: {"OR": FakeLocator(), "1": FakeLocator()},
    )

    with pytest.raises(ValueError, match="available rounds: OR, 1"):
        fixture.navigate_to_round(FakePage(), "GF")


def test_scrape_match_ids_normalises_ids_and_closes_page(monkeypatch):
    page = FakePage()
    matches = [
        FakeLocator(attributes={"data-match-id": "123"}),
        FakeLocator(attributes={"data-match-id": "456"}),
    ]
    page.locators[scrape.FIXTURE_CLASSNAMES["MATCHES"]] = FakeLocator(items=matches)
    monkeypatch.setattr(scrape, "get_fixture_page", lambda _browser, _year: page)
    monkeypatch.setattr(scrape, "navigate_to_round", lambda _page, _round: _page)

    assert scrape.scrape_match_ids(FakeBrowser(), "OR", 2026) == [123, 456]
    assert page.closed is True


def test_scrape_match_rejects_invalid_id_without_opening_page():
    browser = FakeBrowser()

    with pytest.raises(ValueError, match="Invalid AFL match ID"):
        scrape.scrape_match(browser, "not-a-number")

    assert browser.new_page_calls == 0


def test_scrape_match_uses_consistent_raw_path_and_closes_page(monkeypatch, tmp_path):
    page = FakePage()
    browser = FakeBrowser(page)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        scrape, "display_player_stats", lambda current_page: current_page
    )
    monkeypatch.setattr(scrape, "extract_table_data", lambda _page: {"ok": True})

    assert scrape.scrape_match(browser, "123") == {"ok": True}

    assert page.gotos == ["https://www.afl.com.au/afl/matches/123"]
    assert page.closed is True
    raw_dir = tmp_path / "data/raw/afl_official/match/123"
    assert (raw_dir / "home_player_stats.html").read_text() == page.html
    assert (raw_dir / "away_player_stats.html").read_text() == page.html
    assert not (tmp_path / "afl_scraper/data").exists()


def test_scrape_players_deduplicates_and_uses_source_urls(monkeypatch):
    page = FakePage()
    browser = FakeBrowser(page)
    saved_ids = []

    class FakeSource:
        def get_list_page_url(self, year):
            return f"https://example.test/list/{year}"

        def scrape_players_links(self, _page):
            return [
                "/players/A/Ada_One.html",
                "/players/A/Ada_One.html",
                "/players/B/Bob_Two.html",
            ]

        def player_id_from_url(self, url):
            return Path(url).stem

        def get_player_page_url(self, player_id):
            return f"https://example.test/player/{player_id}"

        def scrape_player(self, _page, player_id):
            saved_ids.append(player_id)
            return Path(f"{player_id}.html")

    monkeypatch.setattr(
        scrape.PlayerSourceFactory, "get", lambda _source_name: FakeSource()
    )

    paths = scrape.scrape_players(browser, 2026, "fake_source")

    assert saved_ids == ["Ada_One", "Bob_Two"]
    assert paths == [Path("Ada_One.html"), Path("Bob_Two.html")]
    assert page.gotos == [
        "https://example.test/list/2026",
        "https://example.test/player/Ada_One",
        "https://example.test/player/Bob_Two",
    ]
    assert page.closed is True


def test_scrape_players_closes_page_and_adds_player_context(monkeypatch):
    page = FakePage()

    class FailingSource:
        def get_list_page_url(self, year):
            return f"https://example.test/list/{year}"

        def scrape_players_links(self, _page):
            return ["/players/A/Ada_One.html"]

        def player_id_from_url(self, _url):
            return "Ada_One"

        def get_player_page_url(self, player_id):
            return f"https://example.test/player/{player_id}"

        def scrape_player(self, _page, _player_id):
            raise ValueError("unexpected markup")

    monkeypatch.setattr(
        scrape.PlayerSourceFactory, "get", lambda _source_name: FailingSource()
    )

    with pytest.raises(RuntimeError, match="fake_source player 'Ada_One'"):
        scrape.scrape_players(FakeBrowser(page), 2026, "fake_source")

    assert page.closed is True


def test_afl_tables_player_links_ignore_missing_hrefs_and_deduplicate():
    page = FakePage()
    page.locators["table tbody tr td a"] = FakeLocator(
        items=[
            FakeLocator(attributes={"href": "players/A/Ada_One.html"}),
            FakeLocator(attributes={"href": "players/A/Ada_One.html"}),
            FakeLocator(attributes={"href": None}),
            FakeLocator(attributes={"href": "teams/adelaide.html"}),
        ]
    )

    assert AFLTablesSource().scrape_players_links(page) == ["players/A/Ada_One.html"]


def test_get_team_page_closes_page_when_navigation_fails():
    class FailingPage(FakePage):
        def goto(self, url):
            raise RuntimeError("navigation failed")

    page = FailingPage()

    with pytest.raises(RuntimeError, match="navigation failed"):
        browser_helpers.get_team_page(FakeBrowser(page), "adelaide-crows")

    assert page.closed is True
