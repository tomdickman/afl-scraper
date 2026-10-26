"""Tests for provider-neutral season routing and loading."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from afl_scraper.models import HistoricalReconciliationReport
from afl_scraper.pipelines import season as season_pipeline_module
from afl_scraper.season_routing import season_plan, season_years


def reconciliation(year: int, *, ok: bool) -> HistoricalReconciliationReport:
    return HistoricalReconciliationReport(
        year=year,
        expected_matches=1,
        database_matches=1 if ok else 0,
        expected_player_stats=1,
        database_player_stats=1 if ok else 0,
        missing_match_ids=[] if ok else [f"match-{year}"],
        unexpected_match_ids=[],
        missing_player_stats=[] if ok else [f"match-{year}:player"],
        unexpected_player_stats=[],
        value_mismatches=[],
    )


def test_season_plan_centralizes_source_boundary_and_paths():
    historical = season_plan(2011)
    official = season_plan(2012)

    assert historical.match_source == "australian_football"
    assert historical.sparse_player_stats is True
    assert historical.approved_mapping_path.name == (
        "2011_australian_football_approved.json"
    )
    assert official.match_source == "afl_official"
    assert official.sparse_player_stats is False
    assert official.approved_mapping_path.name == "2012_approved.json"


@pytest.mark.parametrize("year", [2005, 2027])
def test_season_plan_rejects_unconfigured_years(year):
    with pytest.raises(ValueError, match="between 2006 and 2026"):
        season_plan(year)


def test_season_years_is_inclusive_and_rejects_reversed_ranges():
    assert season_years(2011, 2012) == [2011, 2012]
    with pytest.raises(ValueError, match="must not exceed"):
        season_years(2012, 2011)


def test_preflight_routes_each_source_without_cli_conditionals(monkeypatch):
    historical = [object()]
    official = [object(), object()]
    monkeypatch.setattr(
        season_pipeline_module,
        "preflight_historical_season",
        lambda _conn, _year: historical,
    )
    monkeypatch.setattr(
        season_pipeline_module,
        "preflight_official_season",
        lambda _conn, _year: official,
    )

    historical_plan, historical_result = season_pipeline_module.preflight_season(
        object(), 2011
    )
    official_plan, official_result = season_pipeline_module.preflight_season(
        object(), 2012
    )

    assert historical_plan.match_source == "australian_football"
    assert historical_result is historical
    assert official_plan.match_source == "afl_official"
    assert official_result is official


def test_generic_loader_uses_one_transaction_per_complete_match(monkeypatch):
    connection = MagicMock()
    game = Mock()
    game.model_copy.return_value = "persisted-game"
    stat = Mock()
    stat.model_copy.return_value = "persisted-stat"
    prepared = [
        SimpleNamespace(
            source_match_id="official-1",
            game=game,
            player_stats=[stat],
        )
    ]
    monkeypatch.setattr(
        season_pipeline_module,
        "allocate_game_id",
        lambda *_args: (99, True),
    )
    save_identity = Mock()
    monkeypatch.setattr(
        season_pipeline_module, "save_game_source_identity", save_identity
    )
    monkeypatch.setattr(
        season_pipeline_module,
        "save_model",
        Mock(return_value=SimpleNamespace(was_inserted=True)),
    )

    inserted, updated = season_pipeline_module.load_prepared_season(
        connection,
        season_plan(2012),
        prepared,
    )

    assert (inserted, updated) == (1, 0)
    connection.transaction.assert_called_once_with()
    game.model_copy.assert_called_once_with(update={"id": 99})
    stat.model_copy.assert_called_once_with(update={"game_id": 99})
    save_identity.assert_called_once_with(connection, "afl_official", "official-1", 99)


def test_backfill_preflights_entire_range_before_first_write(monkeypatch):
    connection = object()

    @contextmanager
    def pool():
        yield connection

    events = []
    loaded = set()

    def preflight(_conn, year):
        events.append(("preflight", year))
        prepared = [SimpleNamespace(player_stats=[object()])]
        return season_plan(year), prepared

    def reconcile(_conn, plan, _prepared):
        events.append(("reconcile", plan.year))
        return reconciliation(plan.year, ok=plan.year in loaded)

    def load(_conn, plan, _prepared, **_kwargs):
        events.append(("load", plan.year))
        loaded.add(plan.year)
        return 1, 0

    monkeypatch.setattr(season_pipeline_module, "admin_connection_pool", pool)
    monkeypatch.setattr(season_pipeline_module, "preflight_season", preflight)
    monkeypatch.setattr(season_pipeline_module, "reconcile_season", reconcile)
    monkeypatch.setattr(season_pipeline_module, "load_prepared_season", load)

    result = season_pipeline_module.backfill_pipeline(2011, 2012, load=True)

    first_load = next(index for index, event in enumerate(events) if event[0] == "load")
    assert ("preflight", 2011) in events[:first_load]
    assert ("preflight", 2012) in events[:first_load]
    assert result.matches == 2
    assert [report.source for report in result.years] == [
        "australian_football",
        "afl_official",
    ]
