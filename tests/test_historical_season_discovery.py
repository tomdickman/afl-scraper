"""Tests for 2006+ competition rules and official season discovery."""

import json
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

import afl_scraper.cli as cli_module
from afl_scraper.scraper import fixture, scrape
from afl_scraper.scraper.constants import (
    competition_rules_for_year,
    official_season_id,
)
from afl_scraper.scraper.models import DiscoveredRound, SeasonManifest


class MatchLocator:
    def __init__(self, match_id):
        self.match_id = match_id

    def get_attribute(self, name):
        return str(self.match_id) if name == "data-match-id" else None


class MatchList:
    def __init__(self, matches):
        self.matches = matches

    def all(self):
        return [MatchLocator(match_id) for match_id in self.matches]


class SeasonPage:
    def __init__(self, matches_by_round):
        self.matches_by_round = matches_by_round
        self.current_round = None
        self.closed = False

    def locator(self, _selector):
        return MatchList(self.matches_by_round[self.current_round])

    def close(self):
        self.closed = True


def test_competition_rules_cover_each_expansion_and_roster_era():
    rules_2006 = competition_rules_for_year(2006)
    assert len(rules_2006.teams) == 16
    assert "Kangaroos" in rules_2006.teams
    assert "North Melbourne" not in rules_2006.teams
    assert rules_2006.participating_players_per_team == 22

    rules_2011 = competition_rules_for_year(2011)
    assert len(rules_2011.teams) == 17
    assert "Gold Coast" in rules_2011.teams

    rules_2012 = competition_rules_for_year(2012)
    assert len(rules_2012.teams) == 18
    assert "Greater Western Sydney" in rules_2012.teams

    rules_2026 = competition_rules_for_year(2026)
    assert rules_2026.participating_players_per_team == 23
    assert rules_2026.maximum_published_players_per_team == 24

    with pytest.raises(ValueError, match="2006-2026"):
        competition_rules_for_year(2005)
    with pytest.raises(ValueError, match="2006-2026"):
        competition_rules_for_year(2027)


def test_official_fixture_catalogue_has_a_clear_historical_boundary():
    assert official_season_id(2012) == 2
    assert official_season_id(2026) == 85

    with pytest.raises(ValueError, match="coverage starts at 2012"):
        official_season_id(2011)
    with pytest.raises(ValueError, match="No reviewed.*2027"):
        official_season_id(2027)


def test_season_discovery_collects_every_round_and_closes_page(monkeypatch):
    page = SeasonPage({"1": [100, 101], "GF": [199]})
    monkeypatch.setattr(scrape, "get_fixture_page", lambda _browser, _year: page)
    monkeypatch.setattr(
        scrape, "get_round_buttons", lambda _page: {"1": object(), "GF": object()}
    )

    def navigate(current_page, label):
        current_page.current_round = label
        return current_page

    monkeypatch.setattr(scrape, "navigate_to_round", navigate)

    manifest = scrape.discover_official_season(object(), 2012)

    assert manifest.year == 2012
    assert manifest.season_id == 2
    assert manifest.match_count == 3
    assert manifest.rounds == [
        DiscoveredRound(label="1", match_ids=[100, 101]),
        DiscoveredRound(label="GF", match_ids=[199]),
    ]
    assert page.closed is True


def test_season_manifest_rejects_match_ids_repeated_across_rounds(monkeypatch):
    page = SeasonPage({"1": [100], "2": [100]})
    monkeypatch.setattr(scrape, "get_fixture_page", lambda _browser, _year: page)
    monkeypatch.setattr(
        scrape, "get_round_buttons", lambda _page: {"1": object(), "2": object()}
    )

    def navigate(current_page, label):
        current_page.current_round = label
        return current_page

    monkeypatch.setattr(scrape, "navigate_to_round", navigate)

    with pytest.raises(ValidationError, match="more than one round"):
        scrape.discover_official_season(object(), 2012)

    assert page.closed is True


def test_manifest_save_is_year_scoped_and_valid_json(tmp_path):
    manifest = SeasonManifest(
        year=2012,
        season_id=2,
        fixture_url=fixture.get_fixture_url(2012),
        discovered_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        rounds=[DiscoveredRound(label="1", match_ids=[100])],
    )

    path = scrape.save_season_manifest(manifest, tmp_path)

    assert path == tmp_path / "2012/manifest.json"
    assert json.loads(path.read_text())["rounds"] == [
        {"label": "1", "match_ids": [100]}
    ]
    assert not list((tmp_path / "2012").glob(".manifest-*.tmp"))


def test_manifest_rejects_unreviewed_id_and_naive_timestamp():
    with pytest.raises(ValidationError, match="reviewed official ID 2"):
        SeasonManifest(
            year=2012,
            season_id=999,
            fixture_url=fixture.get_fixture_url(2012),
            discovered_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
            rounds=[DiscoveredRound(label="1", match_ids=[100])],
        )

    with pytest.raises(ValidationError, match="timezone"):
        SeasonManifest(
            year=2012,
            season_id=2,
            fixture_url=fixture.get_fixture_url(2012),
            discovered_at=datetime(2026, 8, 15),
            rounds=[DiscoveredRound(label="1", match_ids=[100])],
        )


def test_scrape_season_cli_reports_manifest(monkeypatch, tmp_path):
    manifest = SeasonManifest(
        year=2012,
        season_id=2,
        fixture_url=fixture.get_fixture_url(2012),
        discovered_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        rounds=[DiscoveredRound(label="1", match_ids=[100, 101])],
    )

    @contextmanager
    def browser_context(_headless):
        yield object()

    monkeypatch.setattr(cli_module, "sync_browser_context", browser_context)
    monkeypatch.setattr(
        cli_module, "discover_official_season", lambda _browser, _year: manifest
    )
    path = tmp_path / "2012/manifest.json"
    monkeypatch.setattr(cli_module, "save_season_manifest", lambda _manifest: path)

    result = CliRunner().invoke(cli_module.cli, ["scrape", "season", "2012"])

    assert result.exit_code == 0, result.output
    assert "Saved 2 matches across 1 rounds" in result.output
    assert str(path) in result.output


class RoundButton:
    def __init__(self, text):
        self.text = text

    def inner_text(self):
        return self.text


class RoundNavigation:
    def __init__(self, buttons):
        self.buttons = buttons

    def get_by_role(self, _role):
        return self

    def all(self):
        return self.buttons


class RoundPage:
    def __init__(self, buttons):
        self.buttons = buttons

    def wait_for_selector(self, _selector):
        return None

    def locator(self, _selector):
        return RoundNavigation(self.buttons)


def test_round_discovery_rejects_blank_and_duplicate_labels():
    with pytest.raises(ValueError, match="blank round"):
        fixture.get_round_buttons(RoundPage([RoundButton(" ")]))

    with pytest.raises(ValueError, match="duplicate round"):
        fixture.get_round_buttons(
            RoundPage([RoundButton("Round 1"), RoundButton(" Round 1 ")])
        )
