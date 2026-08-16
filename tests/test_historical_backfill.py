"""Tests for resumable range orchestration and database reconciliation."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from afl_scraper.cli import cli
from afl_scraper.models import (
    Game,
    HistoricalReconciliationReport,
    PlayerGameStats,
)
from afl_scraper.pipelines import historical, historical_backfill


def _prepared(year=2006, source_match_id="13127"):
    game = Game(
        id=1,
        venue="M.C.G.",
        start_date=datetime(year, 3, 24, 8, 30, tzinfo=timezone.utc),
        round="Round 1",
        home_team="Collingwood",
        away_team="Carlton",
        home_goals=10,
        home_behinds=5,
        away_goals=8,
        away_behinds=7,
    )
    stat = PlayerGameStats(
        player_id="Scott_Pendlebury",
        team="Collingwood",
        jumper_number=10,
        kicks=8,
        marks=3,
        handballs=7,
        goals=1,
        behinds=0,
        hitouts=0,
        tackles=2,
        rebound_50s=None,
        inside_50s=None,
        clearances=None,
        clangers=None,
        free_kicks_for=1,
        free_kicks_against=2,
        contested_possessions=None,
        uncontested_possessions=None,
        contested_marks=None,
        marks_inside_50=None,
        one_percenters=None,
        bounces=None,
        goal_assists=None,
        time_on_ground_percent=None,
        fantasy_points=None,
        game_id=1,
    )
    return [historical.PreparedHistoricalMatch(source_match_id, game, [stat])]


def _connection_rows(game_rows, stat_rows):
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.side_effect = [game_rows, stat_rows]
    return connection


def _game_row(prepared, game_id=9000):
    match = prepared[0]
    return (
        match.source_match_id,
        game_id,
        *(getattr(match.game, field) for field in historical._GAME_FIELDS),
    )


def _stat_row(prepared):
    match = prepared[0]
    stat = match.player_stats[0]
    return (
        match.source_match_id,
        *(getattr(stat, field) for field in historical._STAT_FIELDS),
    )


def test_reconciliation_compares_complete_non_null_source_contract():
    prepared = _prepared()
    connection = _connection_rows([_game_row(prepared)], [_stat_row(prepared)])

    report = historical.reconcile_historical_season(connection, 2006, prepared)

    assert report.ok
    assert report.expected_matches == report.database_matches == 1
    assert report.expected_player_stats == report.database_player_stats == 1


def test_reconciliation_reports_missing_unexpected_and_changed_values():
    prepared = _prepared()
    changed_game = list(_game_row(prepared))
    changed_game[-4] = 99  # home_goals
    unexpected = _prepared(source_match_id="99999")
    connection = _connection_rows(
        [tuple(changed_game), _game_row(unexpected, game_id=9001)],
        [_stat_row(unexpected)],
    )

    report = historical.reconcile_historical_season(connection, 2006, prepared)

    assert not report.ok
    assert report.unexpected_match_ids == ["99999"]
    assert report.missing_player_stats == ["13127:Scott_Pendlebury"]
    assert report.unexpected_player_stats == ["99999:Scott_Pendlebury"]
    assert any("home_goals" in mismatch for mismatch in report.value_mismatches)


def _reconciliation(year, ok):
    return HistoricalReconciliationReport(
        year=year,
        expected_matches=1,
        database_matches=1 if ok else 0,
        expected_player_stats=1,
        database_player_stats=1 if ok else 0,
        missing_match_ids=[] if ok else [str(year)],
        missing_player_stats=[] if ok else [f"{year}:player"],
    )


def _pool(connection):
    @contextmanager
    def pool():
        yield connection

    return pool


def test_range_preflights_every_year_before_first_write(monkeypatch, tmp_path):
    events = []
    loaded = set()
    connection = MagicMock()
    monkeypatch.setattr(historical_backfill, "admin_connection_pool", _pool(connection))

    def preflight(_conn, year):
        events.append(("preflight", year))
        return _prepared(year, str(year))

    def reconcile(_conn, year, _prepared_matches):
        events.append(("reconcile", year))
        return _reconciliation(year, year in loaded)

    def load(_conn, year, prepared_matches):
        events.append(("load", year))
        loaded.add(year)
        return historical.HistoricalLoadReport(
            year, len(prepared_matches), 1, False, inserted_games=1
        )

    monkeypatch.setattr(historical_backfill, "preflight_historical_season", preflight)
    monkeypatch.setattr(historical_backfill, "reconcile_historical_season", reconcile)
    monkeypatch.setattr(historical_backfill, "load_prepared_historical_season", load)

    result = historical_backfill.historical_backfill_pipeline(
        2006,
        2007,
        load=True,
        checkpoint_path=tmp_path / "checkpoint.json",
        report_path=tmp_path / "report.json",
    )

    first_load = next(index for index, event in enumerate(events) if event[0] == "load")
    assert events[:first_load] == [
        ("preflight", 2006),
        ("reconcile", 2006),
        ("preflight", 2007),
        ("reconcile", 2007),
    ]
    assert result.report.ok
    assert [result.checkpoint.years[year].status for year in (2006, 2007)] == [
        "loaded",
        "loaded",
    ]
    assert not list(tmp_path.glob(".*.tmp"))


def test_later_preflight_failure_prevents_all_range_database_writes(
    monkeypatch, tmp_path
):
    connection = MagicMock()
    monkeypatch.setattr(historical_backfill, "admin_connection_pool", _pool(connection))

    def preflight(_conn, year):
        if year == 2007:
            raise ValueError("missing 2007 mappings")
        return _prepared(year, str(year))

    monkeypatch.setattr(historical_backfill, "preflight_historical_season", preflight)
    monkeypatch.setattr(
        historical_backfill,
        "reconcile_historical_season",
        lambda _conn, year, _prepared_matches: _reconciliation(year, False),
    )
    load = MagicMock()
    monkeypatch.setattr(historical_backfill, "load_prepared_historical_season", load)
    checkpoint_path = tmp_path / "checkpoint.json"
    report_path = tmp_path / "report.json"

    with pytest.raises(ValueError, match="missing 2007 mappings"):
        historical_backfill.historical_backfill_pipeline(
            2006,
            2007,
            load=True,
            checkpoint_path=checkpoint_path,
            report_path=report_path,
        )

    load.assert_not_called()
    checkpoint = historical_backfill.load_historical_checkpoint(checkpoint_path)
    assert checkpoint.years[2006].status == "validated"
    assert checkpoint.years[2007].status == "failed"
    report = json.loads(report_path.read_text())
    assert report["complete"] is False
    assert report["ok"] is False


def test_resume_skips_only_database_reconciled_years(monkeypatch, tmp_path):
    connection = MagicMock()
    monkeypatch.setattr(historical_backfill, "admin_connection_pool", _pool(connection))
    monkeypatch.setattr(
        historical_backfill,
        "preflight_historical_season",
        lambda _conn, year: _prepared(year, str(year)),
    )
    reconciled = True
    monkeypatch.setattr(
        historical_backfill,
        "reconcile_historical_season",
        lambda _conn, year, _prepared_matches: _reconciliation(year, reconciled),
    )
    load = MagicMock()
    monkeypatch.setattr(historical_backfill, "load_prepared_historical_season", load)
    checkpoint_path = tmp_path / "checkpoint.json"
    report_path = tmp_path / "report.json"

    result = historical_backfill.historical_backfill_pipeline(
        2006,
        2006,
        load=True,
        checkpoint_path=checkpoint_path,
        report_path=report_path,
    )

    load.assert_not_called()
    assert result.checkpoint.years[2006].status == "verified"

    reconciled = False
    with pytest.raises(ValueError, match="reconciliation failed"):
        historical_backfill.historical_backfill_pipeline(
            2006,
            2006,
            load=True,
            checkpoint_path=checkpoint_path,
            report_path=report_path,
        )
    checkpoint = historical_backfill.load_historical_checkpoint(checkpoint_path)
    assert checkpoint.years[2006].status == "failed"
    load.assert_not_called()


def test_dry_run_writes_analysis_but_never_loads(monkeypatch, tmp_path):
    connection = MagicMock()
    monkeypatch.setattr(historical_backfill, "admin_connection_pool", _pool(connection))
    monkeypatch.setattr(
        historical_backfill,
        "preflight_historical_season",
        lambda _conn, year: _prepared(year, str(year)),
    )
    monkeypatch.setattr(
        historical_backfill,
        "reconcile_historical_season",
        lambda _conn, year, _prepared_matches: _reconciliation(year, False),
    )
    load = MagicMock()
    monkeypatch.setattr(historical_backfill, "load_prepared_historical_season", load)

    result = historical_backfill.historical_backfill_pipeline(
        2006,
        2007,
        checkpoint_path=tmp_path / "checkpoint.json",
        report_path=tmp_path / "report.json",
    )

    load.assert_not_called()
    assert not result.report.ok
    assert result.report.dry_run
    assert [result.checkpoint.years[year].status for year in (2006, 2007)] == [
        "validated",
        "validated",
    ]
    report_json = json.loads((tmp_path / "report.json").read_text())
    assert report_json["complete"] is True
    assert report_json["ok"] is False
    assert report_json["expected_matches"] == 2
    assert report_json["database_matches"] == 0
    assert report_json["mismatch_count"] == 4
    assert report_json["years"][0]["mismatch_count"] == 2


def test_reprocess_forces_idempotent_load_even_when_database_matches(
    monkeypatch, tmp_path
):
    connection = MagicMock()
    monkeypatch.setattr(historical_backfill, "admin_connection_pool", _pool(connection))
    monkeypatch.setattr(
        historical_backfill,
        "preflight_historical_season",
        lambda _conn, year: _prepared(year, str(year)),
    )
    monkeypatch.setattr(
        historical_backfill,
        "reconcile_historical_season",
        lambda _conn, year, _prepared_matches: _reconciliation(year, True),
    )
    load = MagicMock(
        return_value=historical.HistoricalLoadReport(2006, 1, 1, False, updated_games=1)
    )
    monkeypatch.setattr(historical_backfill, "load_prepared_historical_season", load)

    result = historical_backfill.historical_backfill_pipeline(
        2006,
        2006,
        load=True,
        resume=False,
        checkpoint_path=tmp_path / "checkpoint.json",
        report_path=tmp_path / "report.json",
    )

    load.assert_called_once()
    assert result.checkpoint.years[2006].updated_games == 1


@pytest.mark.parametrize(
    ("start_year", "end_year"),
    [(2005, 2006), (2011, 2012), (2008, 2007)],
)
def test_range_validation_rejects_unsupported_or_reversed_years(start_year, end_year):
    with pytest.raises(ValueError):
        historical_backfill.validate_historical_year_range(start_year, end_year)


def test_backfill_cli_rejects_unsupported_range_before_database_access():
    result = CliRunner().invoke(
        cli,
        [
            "pipeline",
            "historical-backfill",
            "--from-year",
            "2005",
            "--to-year",
            "2011",
        ],
    )

    assert result.exit_code != 0
    assert "supports 2006-2011" in str(result.exception)
