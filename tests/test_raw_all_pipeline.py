from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import ANY, Mock

import pytest

from afl_scraper.models import PlayerInfo
from afl_scraper.pipelines import raw_all
from afl_scraper.pipelines.historical_players import HistoricalPlayerPreparationReport
from afl_scraper.scraper.models import (
    DiscoveredRound,
    OfficialFixtureMetadata,
    RawMatchData,
    RawMatchDetails,
    RawPlayerStat,
    SeasonManifest,
)


def _stat(player_id, name):
    return RawPlayerStat(
        afl_official_id=player_id,
        player_name=name,
        jumper_number=1,
        kicks=1,
        handballs=1,
        disposals=2,
        marks=1,
        goals=0,
        behinds=0,
        hitouts=0,
        tackles=1,
        clearances=0,
        goal_assists=0,
        time_on_ground_percent=Decimal("80"),
        fantasy_points=10,
    )


def _match(venue="MCG"):
    return RawMatchData(
        details=RawMatchDetails(
            home_team="Carlton",
            away_team="Collingwood",
            round="Round 1",
            date="Saturday 24 March 2012",
            time="7:30 PM (GMT+10)",
            venue=venue,
            status="FULL TIME",
            home_team_goals=1,
            home_team_behinds=1,
            home_team_total=7,
            away_team_goals=1,
            away_team_behinds=2,
            away_team_total=8,
        ),
        home_team_stats=[_stat("101", "Alex Smith")],
        away_team_stats=[_stat("202", "Bob Jones")],
    )


def _manifest():
    return SeasonManifest(
        schema_version=2,
        year=2012,
        season_id=2,
        fixture_url="https://example.test/fixture",
        discovered_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        rounds=[DiscoveredRound(label="1", match_ids=[100])],
        fixtures=[
            OfficialFixtureMetadata(
                match_id=100,
                round="1",
                home_team="Carlton",
                away_team="Collingwood",
                scheduled_at=datetime(2012, 3, 24, 19, 30, tzinfo=timezone.utc),
                venue="MCG",
                home_total=7,
                away_total=8,
                status="COMPLETED",
                source_url="https://www.afl.com.au/afl/matches/100",
            )
        ],
    )


def _legacy_manifest():
    return SeasonManifest(
        year=2012,
        season_id=2,
        fixture_url="https://example.test/fixture",
        discovered_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        rounds=[DiscoveredRound(label="1", match_ids=[100])],
    )


def test_cached_official_range_reuses_manifest_and_match(monkeypatch, tmp_path):
    manifest = _manifest()
    players = [
        PlayerInfo(
            id="101",
            first_name="Alex",
            last_name="Smith",
            team="Carlton",
            year=2012,
        )
    ]

    @contextmanager
    def browser_context(_headless):
        yield object()

    monkeypatch.setattr(raw_all, "CATALOG_ROOT", tmp_path / "catalog")
    monkeypatch.setattr(raw_all, "sync_browser_context", browser_context)
    monkeypatch.setattr(
        raw_all,
        "prepare_player_raw_data",
        Mock(
            return_value=HistoricalPlayerPreparationReport(2012, 2012, 1, 1, 0, 1, True)
        ),
    )
    monkeypatch.setattr(raw_all, "load_season_manifest", Mock(return_value=manifest))
    discover = Mock()
    monkeypatch.setattr(raw_all, "discover_official_season", discover)
    scrape = Mock(return_value=players)
    monkeypatch.setattr(raw_all, "scrape_season_player_ids", scrape)
    monkeypatch.setattr(raw_all, "load_raw_match_data", Mock(return_value=_match()))
    save_players = Mock()
    monkeypatch.setattr(raw_all, "save_player_ids_to_json", save_players)

    report = raw_all.scrape_all_raw_data(2012, 2012, delay_ms=0)

    assert report.matches == 1
    assert report.player_stats == 2
    discover.assert_not_called()
    scrape.assert_called_once_with(
        ANY,
        manifest,
        refresh=False,
        progress=ANY,
    )
    save_players.assert_called_once_with(players, "afl_official", 2012)
    assert (tmp_path / "catalog" / "2012.json").exists()
    assert (tmp_path / "catalog" / "2012-2012-report.json").exists()


def test_legacy_official_manifest_is_refreshed_for_metadata_fallback(
    monkeypatch, tmp_path
):
    enriched = _manifest()

    @contextmanager
    def browser_context(_headless):
        yield object()

    monkeypatch.setattr(raw_all, "CATALOG_ROOT", tmp_path / "catalog")
    monkeypatch.setattr(raw_all, "sync_browser_context", browser_context)
    monkeypatch.setattr(
        raw_all,
        "prepare_player_raw_data",
        Mock(
            return_value=HistoricalPlayerPreparationReport(2012, 2012, 1, 1, 0, 1, True)
        ),
    )
    monkeypatch.setattr(
        raw_all, "load_season_manifest", Mock(return_value=_legacy_manifest())
    )
    discover = Mock(return_value=enriched)
    monkeypatch.setattr(raw_all, "discover_official_season", discover)
    save_manifest = Mock()
    monkeypatch.setattr(raw_all, "save_season_manifest", save_manifest)
    monkeypatch.setattr(
        raw_all,
        "scrape_season_player_ids",
        Mock(
            return_value=[
                PlayerInfo(
                    id="101",
                    first_name="Alex",
                    last_name="Smith",
                    team="Carlton",
                    year=2012,
                )
            ]
        ),
    )
    monkeypatch.setattr(raw_all, "load_raw_match_data", Mock(return_value=_match()))
    monkeypatch.setattr(raw_all, "save_player_ids_to_json", Mock())

    raw_all.scrape_all_raw_data(2012, 2012, delay_ms=0)

    discover.assert_called_once()
    save_manifest.assert_called_once_with(enriched)
    raw_all.scrape_season_player_ids.assert_called_once_with(
        ANY,
        enriched,
        refresh=False,
        progress=ANY,
    )


def test_catalog_rejects_unmapped_venue(monkeypatch, tmp_path):
    monkeypatch.setattr(raw_all, "CATALOG_ROOT", tmp_path)
    monkeypatch.setattr(
        raw_all, "load_raw_match_data", Mock(return_value=_match("Mystery Ground"))
    )

    with pytest.raises(KeyError, match="No venue mapping found"):
        raw_all._write_official_catalog(2012, _manifest(), [])

    assert not (tmp_path / "2012.json").exists()


@pytest.mark.parametrize("years", [(2005, 2006), (2026, 2027), (2012, 2011)])
def test_raw_range_is_bounded_before_browser_or_database(monkeypatch, years):
    browser = Mock()
    monkeypatch.setattr(raw_all, "sync_browser_context", browser)

    with pytest.raises(ValueError):
        raw_all.scrape_all_raw_data(*years)

    browser.assert_not_called()
