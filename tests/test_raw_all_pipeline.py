import json
from contextlib import contextmanager
from datetime import date, datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import ANY, Mock

import pytest
from click.testing import CliRunner

from afl_scraper.cli import cli
from afl_scraper.models import PlayerInfo
from afl_scraper.pipelines import raw_all
from afl_scraper.pipelines.historical_players import HistoricalPlayerPreparationReport
from afl_scraper.scraper.models import (
    DiscoveredRound,
    MatchMetadataCatalog,
    MatchMetadataRecord,
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


def _tables_catalog():
    return MatchMetadataCatalog(
        year=2012,
        source_url="https://afltables.com/afl/seas/2012.html",
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        matches=[
            MatchMetadataRecord(
                source_match_id="test-match",
                source_url="https://afltables.com/afl/stats/games/2012/test-match.html",
                year=2012,
                round="Round 1",
                home_team="Carlton",
                away_team="Collingwood",
                local_date=date(2012, 3, 24),
                local_time=time(19, 30),
                venue="M.C.G.",
                home_goals=1,
                home_behinds=1,
                home_total=7,
                away_goals=1,
                away_behinds=2,
                away_total=8,
            )
        ],
    )


def _mock_secondary_sources(monkeypatch):
    monkeypatch.setattr(raw_all, "MAX_AVAILABLE_YEAR", 2011)
    monkeypatch.setattr(raw_all, "load_player_snapshot", Mock(return_value=[]))
    monkeypatch.setattr(
        raw_all, "get_match_metadata_catalog", Mock(return_value=_tables_catalog())
    )
    monkeypatch.setattr(
        raw_all, "cache_afl_tables_season_matches", Mock(return_value=2)
    )
    monkeypatch.setattr(
        raw_all,
        "audit_match_metadata",
        Mock(return_value={"match_count": 1, "resolved_count": 1, "unresolved_count": 0}),
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
    _mock_secondary_sources(monkeypatch)
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
    _mock_secondary_sources(monkeypatch)
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


@pytest.mark.parametrize(
    "years",
    [
        (raw_all.MIN_HISTORY_YEAR - 1, raw_all.MIN_HISTORY_YEAR),
        (raw_all.MAX_CONFIGURED_YEAR, raw_all.MAX_CONFIGURED_YEAR + 1),
        (raw_all.MIN_HISTORY_YEAR + 1, raw_all.MIN_HISTORY_YEAR),
    ],
)
def test_raw_range_is_bounded_before_browser_or_database(monkeypatch, years):
    browser = Mock()
    monkeypatch.setattr(raw_all, "sync_browser_context", browser)

    with pytest.raises(ValueError):
        raw_all.scrape_all_raw_data(*years)

    browser.assert_not_called()


def test_scrape_all_help_promises_no_postgresql_access():
    result = CliRunner().invoke(cli, ["scrape", "all", "--help"])

    assert result.exit_code == 0
    assert "without PostgreSQL access" in result.output


def test_year_manifest_records_complete_and_unavailable_sources(monkeypatch, tmp_path):
    monkeypatch.setattr(raw_all, "CATALOG_ROOT", tmp_path)
    reports = [
        raw_all.RawSeasonReport(
            2006, "afl_tables", 185, 0, 600, 16, 12, "tables.json"
        ),
        raw_all.RawSeasonReport(
            2006, "australian_football", 185, 8140, 600, 16, 12, "af.json"
        ),
    ]

    path = raw_all._write_year_manifest(2006, reports, [{"resolved_count": 185}])
    payload = json.loads(path.read_text())

    assert payload["schema_version"] == 2
    assert payload["cross_source_validations"] == [{"resolved_count": 185}]
    sources = {item["source"]: item for item in payload["sources"]}
    assert sources["afl_tables"]["status"] == "complete"
    assert sources["australian_football"]["status"] == "complete"
    assert sources["afl_official"]["status"] == "unavailable"
    assert "starts in 2012" in sources["afl_official"]["reason"]


def test_report_counts_distinct_matches_instead_of_duplicate_sources():
    report = raw_all.RawScrapeReport(
        2012,
        2012,
        (
            raw_all.RawSeasonReport(2012, "afl_tables", 207, 0, 1, 18, 20, "a"),
            raw_all.RawSeasonReport(2012, "afl_official", 207, 9108, 1, 18, 20, "b"),
            raw_all.RawSeasonReport(
                2012, "australian_football", 207, 9108, 1, 18, 20, "c"
            ),
        ),
        1,
        0,
        1,
    )

    assert report.years == 1
    assert report.sources == 3
    assert report.matches == 207
    assert report.player_stats == 9108


def test_historical_audit_records_source_score_conflicts(monkeypatch):
    details = SimpleNamespace(
        home_team="Carlton",
        away_team="Collingwood",
        date=date(2012, 3, 24),
        local_time=time(19, 30),
        venue="M.C.G.",
        home_team_goals=1,
        home_team_behinds=1,
        home_team_total=7,
        away_team_goals=1,
        away_team_behinds=3,
        away_team_total=9,
    )
    monkeypatch.setattr(
        raw_all,
        "load_australian_football_match",
        Mock(return_value=SimpleNamespace(details=details)),
    )

    report = raw_all._historical_metadata_audit(
        2012, _manifest(), _tables_catalog()
    )

    assert report["status"] == "conflict"
    assert report["resolved_count"] == 1
    assert report["unresolved_count"] == 0
    assert report["conflict_count"] == 1
    assert report["conflicts"][0]["differences"] == {
        "away_behinds": {"australian_football": 3, "afl_tables": 2},
        "away_total": {"australian_football": 9, "afl_tables": 8},
    }
    assert report["conflicts"][0]["score_validation"] == {
        "australian_football": {
            "home": {
                "goals": 1,
                "behinds": 1,
                "published_total": 7,
                "calculated_total": 7,
                "valid": True,
            },
            "away": {
                "goals": 1,
                "behinds": 3,
                "published_total": 9,
                "calculated_total": 9,
                "valid": True,
            },
        },
        "afl_tables": {
            "home": {
                "goals": 1,
                "behinds": 1,
                "published_total": 7,
                "calculated_total": 7,
                "valid": True,
            },
            "away": {
                "goals": 1,
                "behinds": 2,
                "published_total": 8,
                "calculated_total": 8,
                "valid": True,
            },
        },
    }

    raw_all._add_official_consensus(report, _manifest())

    assert report["conflicts"][0]["resolution"] == {
        "status": "resolved_by_official_corroboration",
        "agreeing_sources": ["afl_official", "afl_tables"],
        "outlier_sources": ["australian_football"],
    }
