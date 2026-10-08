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
from afl_scraper.scraper.constants import official_season_id
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


def manifest(match_ids=(100, 101), *, year=2012) -> SeasonManifest:
    season_id = official_season_id(year)
    return SeasonManifest(
        year=year,
        season_id=season_id,
        fixture_url=(
            f"https://www.afl.com.au/fixture?Competition=1&Season={season_id}"
        ),
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
    ("short_name", "formal_name"),
    [
        ("Matt Shaw", "Matthew Shaw"),
        ("Nat Fyfe", "Nathan Fyfe"),
        ("Paddy Ryder", "Patrick Ryder"),
    ],
)
def test_match_identities_accept_source_name_alias_and_keep_formal_name(
    short_name, formal_name
):
    identities = {}

    season_identities.collect_match_identities(
        identities, raw_match(home_name=short_name), 100, 2012
    )
    season_identities.collect_match_identities(
        identities, raw_match(home_name=formal_name), 101, 2012
    )

    assert identities["101"].display_name() == formal_name


def test_match_identity_given_name_shortening_still_requires_same_surname():
    identities = {}
    season_identities.collect_match_identities(
        identities, raw_match(home_name="Matt Shaw"), 100, 2012
    )

    with pytest.raises(ValueError, match="Conflicting AFL official identity 101"):
        season_identities.collect_match_identities(
            identities, raw_match(home_name="Matthew Smith"), 101, 2012
        )


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

    def scrape_live(_browser, match_id, **_kwargs):
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


def test_missing_fallback_identity_is_retried_after_later_matches(monkeypatch):
    calls = []
    progress = []
    ceglar_match = raw_match(
        year=2012,
        home_team="Hawthorn",
        home_name="Jonathon Ceglar",
        home_id="303",
    )

    monkeypatch.setattr(
        season_identities,
        "load_raw_match_data",
        lambda _match_id: (_ for _ in ()).throw(FileNotFoundError()),
    )

    def scrape_live(_browser, match_id, *, player_identities, **_kwargs):
        calls.append((match_id, {player.id for player in player_identities}))
        if match_id == 100 and "303" not in calls[-1][1]:
            identity_error = ValueError(
                "AFL Tables player 'Jonathon Ceglar' for Hawthorn resolved to "
                "0 official identities; candidates=none"
            )
            raise RuntimeError("Failed to scrape AFL match 100") from identity_error
        return ceglar_match

    monkeypatch.setattr(season_identities, "scrape_match", scrape_live)

    players = season_identities.scrape_season_player_ids(
        object(),
        manifest(),
        progress=lambda *values: progress.append(values),
    )

    assert calls == [(100, set()), (101, set()), (100, {"202", "303"})]
    assert [player.id for player in players] == ["202", "303"]
    assert progress == [(2, 2, 101, False), (1, 2, 100, False)]


def test_unresolved_fallback_identity_fails_after_full_retry_pass(monkeypatch):
    calls = []
    monkeypatch.setattr(
        season_identities,
        "load_raw_match_data",
        lambda _match_id: (_ for _ in ()).throw(FileNotFoundError()),
    )

    def scrape_live(_browser, match_id, **_kwargs):
        calls.append(match_id)
        identity_error = ValueError(
            "AFL Tables player 'Unknown Player' for Hawthorn resolved to "
            "0 official identities; candidates=none"
        )
        raise RuntimeError(f"Failed to scrape AFL match {match_id}") from identity_error

    monkeypatch.setattr(season_identities, "scrape_match", scrape_live)

    with pytest.raises(
        RuntimeError,
        match=(
            "Could not resolve AFL Official identities for deferred matches 100 "
            "after scanning every match in 2012"
        ),
    ) as raised:
        season_identities.scrape_season_player_ids(
            object(), manifest((100,))
        )

    assert calls == [100, 100]
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert "resolved to 0 official identities" in str(
        raised.value.__cause__.__cause__
    )


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
        lambda _browser, match_id, **_kwargs: live_calls.append(match_id),
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


@pytest.mark.parametrize("year", [2012, 2026])
def test_scrape_season_mapping_cli_promotes_both_sources_together(
    monkeypatch, tmp_path, year
):
    class CurrentDate:
        @classmethod
        def now(cls):
            return datetime(2026, 10, 3)

    official = PlayerInfo(
        id="101",
        first_name="Alex",
        last_name="Smith",
        team="Carlton",
        year=year,
    )
    tables = official.model_copy(update={"id": "Alex_Smith"})
    saved = {}

    @contextmanager
    def browser_context(_headless):
        yield object()

    monkeypatch.setattr(cli_module, "datetime", CurrentDate)
    monkeypatch.setattr(cli_module, "sync_browser_context", browser_context)
    monkeypatch.setattr(
        scraper_package,
        "load_season_manifest",
        lambda requested_year: manifest(year=requested_year),
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
        cli_module.cli, ["map", "scrape-season", "--year", str(year)]
    )

    assert result.exit_code == 0, result.output
    assert saved == {"afl_official": [official], "afl_tables": [tables]}


def test_scrape_season_mapping_cli_rejects_future_year_before_manifest(monkeypatch):
    class CurrentDate:
        @classmethod
        def now(cls):
            return datetime(2026, 10, 3)

    manifest_calls = []
    monkeypatch.setattr(cli_module, "datetime", CurrentDate)
    monkeypatch.setattr(
        scraper_package,
        "load_season_manifest",
        lambda year: manifest_calls.append(year),
    )

    result = CliRunner().invoke(
        cli_module.cli, ["map", "scrape-season", "--year", "2027"]
    )

    assert result.exit_code == 2
    assert "cannot process a future season" in result.output
    assert manifest_calls == []


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
