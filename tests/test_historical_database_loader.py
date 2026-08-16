"""Reliability tests for source-qualified historical database loading."""

from contextlib import contextmanager
from datetime import date, time, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from afl_scraper.cli import cli
from afl_scraper.models import HistoricalReconciliationReport, SourcePlayerMapping
from afl_scraper.pipelines import historical
from afl_scraper.scraper.models import (
    AustralianFootballMatchData,
    AustralianFootballMatchDetails,
    AustralianFootballPlayerStat,
)
from afl_scraper.storage import SaveResult
from afl_scraper.transform.australian_football import (
    transform_australian_football_match,
)
from afl_scraper.transform.source_mappings import validate_source_mapping_coverage


def _stat(source_id: str, name: str, *, free_for: int = 1):
    return AustralianFootballPlayerStat(
        source_player_id=source_id,
        player_name=name,
        jumper_number=10,
        kicks=8,
        marks=3,
        handballs=7,
        disposals=15,
        goals=1,
        behinds=0,
        hitouts=0,
        tackles=2,
        free_kicks_for=free_for,
        free_kicks_against=2,
    )


def _match(*, venue="M.C.G.", away_team="Carlton"):
    return AustralianFootballMatchData(
        details=AustralianFootballMatchDetails(
            home_team="Collingwood",
            away_team=away_team,
            round="Round 1",
            date=date(2006, 3, 24),
            local_time=time(19, 30),
            venue=venue,
            home_team_goals=10,
            home_team_behinds=5,
            home_team_total=65,
            away_team_goals=8,
            away_team_behinds=7,
            away_team_total=55,
        ),
        home_team_stats=[_stat("14797", "Scott Pendlebury")],
        away_team_stats=[_stat("200", "Alex Example", free_for=3)],
    )


def test_historical_transform_uses_date_aware_venue_timezone_and_sparse_stats():
    game, stats = transform_australian_football_match(
        _match(),
        game_id=9000,
        player_id_map={"14797": "Scott_Pendlebury", "200": "Alex_Example"},
    )

    assert game.venue == "M.C.G."
    assert game.start_date.utcoffset() == timedelta(hours=11)
    assert game.start_date.isoformat() == "2006-03-24T19:30:00+11:00"
    assert stats[0].player_id == "Scott_Pendlebury"
    assert stats[0].free_kicks_for == 1
    assert stats[0].clearances is None
    assert stats[0].goal_assists is None
    assert stats[0].time_on_ground_percent is None
    assert stats[0].fantasy_points is None


def test_historical_transform_accepts_real_source_team_punctuation():
    game, _ = transform_australian_football_match(
        _match(away_team="St. Kilda"),
        game_id=9000,
        player_id_map={"14797": "Scott_Pendlebury", "200": "Alex_Example"},
    )

    assert game.away_team == "St Kilda"


def test_historical_transform_fails_closed_on_unknown_venue_and_identity_alias():
    with pytest.raises(KeyError, match="No venue mapping"):
        transform_australian_football_match(
            _match(venue="Mystery Ground"),
            game_id=1,
            player_id_map={"14797": "one", "200": "two"},
        )

    with pytest.raises(ValueError, match="aliases two participants"):
        transform_australian_football_match(
            _match(),
            game_id=1,
            player_id_map={"14797": "same", "200": "same"},
        )


def test_source_mapping_coverage_rejects_missing_extra_and_aliases():
    with pytest.raises(ValueError, match="missing 1: 200; unexpected 1: 999"):
        validate_source_mapping_coverage(
            {"14797", "200"},
            [
                SourcePlayerMapping(
                    source_player_id="14797", player_id="Scott_Pendlebury"
                ),
                SourcePlayerMapping(source_player_id="999", player_id="Other"),
            ],
        )

    with pytest.raises(ValueError, match="Duplicate canonical player ID"):
        validate_source_mapping_coverage(
            {"14797", "200"},
            [
                SourcePlayerMapping(source_player_id="14797", player_id="same"),
                SourcePlayerMapping(source_player_id="200", player_id="same"),
            ],
        )


def _pool(connection):
    @contextmanager
    def pool():
        yield connection

    return pool


def test_replaying_historical_season_reuses_internal_game_identity(monkeypatch):
    game, stats = transform_australian_football_match(
        _match(),
        game_id=1,
        player_id_map={"14797": "Scott_Pendlebury", "200": "Alex_Example"},
    )
    prepared = [historical.PreparedHistoricalMatch("13127", game, stats)]
    connection = MagicMock()
    monkeypatch.setattr(historical, "admin_connection_pool", _pool(connection))
    monkeypatch.setattr(
        historical, "preflight_historical_season", lambda *_args: prepared
    )
    allocations = iter([(9000, True), (9000, False)])
    monkeypatch.setattr(
        historical, "allocate_game_id", lambda *_args: next(allocations)
    )
    saved_identities = []
    monkeypatch.setattr(
        historical,
        "save_game_source_identity",
        lambda *args: saved_identities.append(args[1:]),
    )
    game_writes = iter([True, False])

    def save(_conn, model):
        if model.__table_name__ == "game":
            return SaveResult(next(game_writes), {"id": model.id})
        return SaveResult(
            False, {"player_id": model.player_id, "game_id": model.game_id}
        )

    monkeypatch.setattr(historical, "save_model", save)
    monkeypatch.setattr(
        historical,
        "reconcile_historical_season",
        lambda *_args: HistoricalReconciliationReport(
            year=2006,
            expected_matches=1,
            database_matches=1,
            expected_player_stats=2,
            database_player_stats=2,
        ),
    )

    first = historical.historical_season_pipeline(2006, load=True)
    second = historical.historical_season_pipeline(2006, load=True)

    assert (first.inserted_games, first.updated_games) == (1, 0)
    assert (second.inserted_games, second.updated_games) == (0, 1)
    assert saved_identities == [("australian_football", "13127", 9000)]
    assert connection.transaction.call_count == 2


def test_dry_run_preflights_without_allocating_or_writing(monkeypatch):
    connection = MagicMock()
    monkeypatch.setattr(historical, "admin_connection_pool", _pool(connection))
    monkeypatch.setattr(
        historical,
        "preflight_historical_season",
        lambda *_args: [
            historical.PreparedHistoricalMatch(
                "13127",
                MagicMock(),
                [MagicMock(), MagicMock()],
            )
        ],
    )
    allocate = MagicMock()
    save = MagicMock()
    monkeypatch.setattr(historical, "allocate_game_id", allocate)
    monkeypatch.setattr(historical, "save_model", save)

    report = historical.historical_season_pipeline(2006)

    assert report == historical.HistoricalLoadReport(2006, 1, 2, True)
    allocate.assert_not_called()
    save.assert_not_called()
    connection.transaction.assert_not_called()


def test_historical_review_writes_source_qualified_approval(tmp_path):
    review = tmp_path / "review.json"
    review.write_text(
        """
        {
          "exact": [{
            "afl": {"id": "14797", "firstName": "Scott", "lastName": "Pendlebury", "team": "Collingwood", "year": 2006},
            "tables": {"id": "Scott_Pendlebury", "firstName": "Scott", "lastName": "Pendlebury", "team": "Collingwood", "year": 2006}
          }],
          "fuzzy": [],
          "unmatched_afl": [],
          "unmatched_tables": []
        }
        """
    )

    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            [
                "map",
                "review-historical",
                "--year",
                "2006",
                "--input",
                str(review),
            ],
        )
        approved = Path(
            "data/mapping/2006_australian_football_approved.json"
        ).read_text()

    assert result.exit_code == 0, result.output
    assert '"source_player_id": "14797"' in approved
    assert '"player_id": "Scott_Pendlebury"' in approved
    assert "afl_official_id" not in approved
