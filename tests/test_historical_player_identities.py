"""Tests for match-derived historical AFL Official identities."""

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import importlib

import pytest
from click.testing import CliRunner

import afl_scraper.cli as cli_module
from afl_scraper.transform import map_players
from afl_scraper.models.player import PlayerInfo, PlayerMapping
from afl_scraper.scraper import scrape, season_identities
from afl_scraper.scraper.models import (
    DiscoveredRound,
    RawMatchData,
    RawMatchDetails,
    RawPlayerStat,
    SeasonManifest,
)
from afl_scraper.transform.map_players import validate_mapping_coverage


scraper_package = importlib.import_module("afl_scraper.scraper")
snapshot_module = importlib.import_module("afl_scraper.scraper.scrape_player_ids")


def stat(official_id: str, name: str) -> RawPlayerStat:
    return RawPlayerStat(
        afl_official_id=official_id,
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


def raw_match(
    year=2012,
    home_team="Carlton",
    away_team="Collingwood",
    home_name="Alex Smith",
    home_id="101",
) -> RawMatchData:
    return RawMatchData(
        details=RawMatchDetails(
            home_team=home_team,
            away_team=away_team,
            round="Round 1",
            date=f"Saturday 24 March {year}",
            time="7:30 PM (GMT+10)",
            venue="MCG",
            status="FULL TIME",
            home_team_goals=1,
            home_team_behinds=1,
            home_team_total=7,
            away_team_goals=1,
            away_team_behinds=2,
            away_team_total=8,
        ),
        home_team_stats=[stat(home_id, home_name)],
        away_team_stats=[stat("202", "Bob Jones")],
    )


def manifest(match_ids=(100, 101)) -> SeasonManifest:
    return SeasonManifest(
        year=2012,
        season_id=2,
        fixture_url="https://www.afl.com.au/fixture?Competition=1&Season=2",
        discovered_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        rounds=[DiscoveredRound(label="1", match_ids=list(match_ids))],
    )


def test_match_identities_deduplicate_benign_name_punctuation():
    identities = {}

    season_identities.collect_match_identities(
        identities, raw_match(home_name="Darcy O'Brien"), 100, 2012
    )
    season_identities.collect_match_identities(
        identities, raw_match(home_name="Darcy OBrien"), 101, 2012
    )

    assert set(identities) == {"101", "202"}
    assert identities["101"].display_name() == "Darcy O'Brien"
    assert identities["101"].team == "Carlton"


def test_match_identities_tolerate_middle_initial_and_suffix_presentation():
    identities = {}

    season_identities.collect_match_identities(
        identities, raw_match(home_name="Josh P. Kennedy Jr"), 100, 2012
    )
    season_identities.collect_match_identities(
        identities, raw_match(home_name="Josh Kennedy"), 101, 2012
    )

    assert identities["101"].display_name() == "Josh P. Kennedy Jr"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"home_name": "Another Person"}, "Conflicting AFL official identity 101"),
        ({"home_team": "Essendon"}, "Conflicting AFL official identity 101"),
    ],
)
def test_match_identity_conflicts_fail_closed(change, message):
    identities = {}
    season_identities.collect_match_identities(identities, raw_match(), 100, 2012)

    with pytest.raises(ValueError, match=message):
        season_identities.collect_match_identities(
            identities, raw_match(**change), 101, 2012
        )


def test_match_from_wrong_year_is_rejected_before_collecting_players():
    identities = {}

    with pytest.raises(ValueError, match="belongs to 2013, expected 2012"):
        season_identities.collect_match_identities(
            identities, raw_match(year=2013), 100, 2012
        )

    assert identities == {}


def test_season_identity_scrape_reuses_cache_and_fetches_only_missing_matches(
    monkeypatch,
):
    cached_match = raw_match(home_name="Alex Smith", home_id="101")
    live_match = raw_match(home_name="Chris Smith", home_id="303")
    live_calls = []
    progress = []

    def load(match_id):
        if match_id == 100:
            return cached_match
        raise FileNotFoundError

    def scrape_live(_browser, match_id):
        live_calls.append(match_id)
        return live_match

    monkeypatch.setattr(season_identities, "load_raw_match_data", load)
    monkeypatch.setattr(season_identities, "scrape_match", scrape_live)

    players = season_identities.scrape_season_player_ids(
        object(),
        manifest(),
        progress=lambda *values: progress.append(values),
    )

    assert [player.id for player in players] == ["101", "202", "303"]
    assert live_calls == [101]
    assert progress == [(1, 2, 100, True), (2, 2, 101, False)]


def test_invalid_cache_fails_instead_of_silently_refreshing(monkeypatch):
    live_calls = []
    monkeypatch.setattr(
        season_identities,
        "load_raw_match_data",
        lambda _match_id: (_ for _ in ()).throw(ValueError("invalid cache")),
    )
    monkeypatch.setattr(
        season_identities,
        "scrape_match",
        lambda _browser, match_id: live_calls.append(match_id),
    )

    with pytest.raises(ValueError, match="invalid cache"):
        season_identities.scrape_season_player_ids(object(), manifest((100,)))

    assert live_calls == []


def test_validated_raw_match_cache_round_trips_atomically(tmp_path):
    path = scrape.save_raw_match_data(raw_match(), 100, tmp_path)

    assert path == tmp_path / "100/match.json"
    assert scrape.load_raw_match_data(100, tmp_path) == raw_match()
    assert not list((tmp_path / "100").glob(".match-*.tmp"))


def test_raw_match_cache_cannot_be_reused_under_another_match_id(tmp_path):
    source_path = scrape.save_raw_match_data(raw_match(), 101, tmp_path)
    wrong_path = tmp_path / "100/match.json"
    wrong_path.parent.mkdir(parents=True)
    wrong_path.write_text(source_path.read_text())

    with pytest.raises(ValueError, match="contains match 101, expected 100"):
        scrape.load_raw_match_data(100, tmp_path)


def test_season_manifest_load_is_year_scoped_and_revalidated(tmp_path):
    path = tmp_path / "2012/manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text(manifest().model_dump_json())

    assert scrape.load_season_manifest(2012, tmp_path) == manifest()

    with pytest.raises(FileNotFoundError, match="scrape season 2013"):
        scrape.load_season_manifest(2013, tmp_path)


def test_complete_mapping_gate_reports_every_missing_participant():
    required = [
        PlayerInfo(
            id=player_id,
            first_name="Alex",
            last_name="Smith",
            team="Carlton",
            year=2012,
        )
        for player_id in ("101", "202")
    ]

    with pytest.raises(ValueError, match="Missing 1.*202"):
        validate_mapping_coverage(
            required,
            [PlayerMapping(afl_official_id="101", player_id="Alex_Smith")],
        )

    validate_mapping_coverage(
        required,
        [
            PlayerMapping(afl_official_id="101", player_id="Alex_Smith"),
            PlayerMapping(afl_official_id="202", player_id="Bob_Jones"),
        ],
    )


def test_scrape_season_mapping_cli_promotes_both_sources_together(
    monkeypatch, tmp_path
):
    official = PlayerInfo(
        id="101",
        first_name="Alex",
        last_name="Smith",
        team="Carlton",
        year=2012,
    )
    tables = official.model_copy(update={"id": "Alex_Smith"})
    saved = {}

    @contextmanager
    def browser_context(_headless):
        yield object()

    monkeypatch.setattr(cli_module, "sync_browser_context", browser_context)
    monkeypatch.setattr(
        scraper_package, "load_season_manifest", lambda _year: manifest()
    )
    monkeypatch.setattr(
        scraper_package,
        "scrape_season_player_ids",
        lambda *_args, **_kwargs: [official],
    )
    monkeypatch.setattr(
        snapshot_module,
        "scrape_player_ids",
        lambda *_args, **_kwargs: [tables],
    )

    def save_snapshots(snapshots, year):
        saved.update(snapshots)
        return {source: tmp_path / f"{year}_{source}.json" for source in snapshots}

    monkeypatch.setattr(
        snapshot_module,
        "save_player_id_snapshots",
        save_snapshots,
    )

    result = CliRunner().invoke(
        cli_module.cli, ["map", "scrape-season", "--year", "2012"]
    )

    assert result.exit_code == 0, result.output
    assert saved == {"afl_official": [official], "afl_tables": [tables]}


def test_mapping_upsert_complete_gate_runs_before_database(monkeypatch, tmp_path):
    approved_path = tmp_path / "2012_approved.json"
    approved_path.write_text('[{"afl_official_id": "101", "player_id": "Alex_Smith"}]')
    required = [
        PlayerInfo(
            id=player_id,
            first_name="Alex",
            last_name="Smith",
            team="Carlton",
            year=2012,
        )
        for player_id in ("101", "202")
    ]
    database_calls = []
    monkeypatch.setattr(
        map_players,
        "load_player_ids_from_json",
        lambda _source, _year: required,
    )
    monkeypatch.setattr(
        map_players,
        "upsert_mappings",
        lambda *_args: database_calls.append(True),
    )

    result = CliRunner().invoke(
        cli_module.cli,
        [
            "map",
            "upsert",
            "--year",
            "2012",
            "--input",
            str(approved_path),
            "--require-complete",
        ],
    )

    assert result.exit_code != 0
    assert "Missing 1 participating AFL official mappings: 202" in str(result.exception)
    assert database_calls == []
