from contextlib import contextmanager
from datetime import datetime
from unittest.mock import ANY, MagicMock, Mock, call

import pytest
from click.testing import CliRunner

import afl_scraper.cli as cli_module
import afl_scraper.pipelines as pipelines_package
from afl_scraper.models import Player, PlayerInfo
from afl_scraper.pipelines import historical_players
from afl_scraper.storage import SaveResult


def snapshot_player(player_id="Alex_Smith", year=2006, team="Carlton"):
    return PlayerInfo(
        id=player_id,
        first_name="Alex",
        last_name="Smith",
        team=team,
        year=year,
    )


def database_player(player_id="Alex_Smith"):
    return Player(
        id=player_id,
        givenname="Alex",
        familyname="Smith",
        birthdate=datetime(1980, 1, 1),
    )


@pytest.mark.parametrize(
    ("start_year", "end_year"),
    [(2005, 2006), (2011, 2012), (2008, 2007)],
)
def test_historical_player_range_is_bounded(start_year, end_year):
    with pytest.raises(ValueError):
        historical_players.validate_historical_player_range(start_year, end_year)


def test_offline_missing_snapshot_fails_without_opening_browser(monkeypatch):
    monkeypatch.setattr(
        historical_players,
        "_load_snapshot",
        Mock(side_effect=FileNotFoundError("missing")),
    )

    with pytest.raises(FileNotFoundError, match="2006"):
        historical_players.prepare_historical_players(2006, 2006, offline=True)


def test_live_snapshot_range_retains_completed_year_for_resume(monkeypatch):
    @contextmanager
    def browser_context(_headless):
        yield object()

    scrape = Mock(
        side_effect=[
            [snapshot_player(year=2006)],
            RuntimeError("source failed"),
        ]
    )
    save = Mock()
    monkeypatch.setattr(historical_players, "sync_browser_context", browser_context)
    monkeypatch.setattr(historical_players, "scrape_player_ids", scrape)
    monkeypatch.setattr(historical_players, "save_player_id_snapshot_range", save)

    with pytest.raises(RuntimeError, match="source failed"):
        historical_players._fetch_snapshots(
            [2006, 2007], refresh=False, delay_ms=0, headless=True
        )

    save.assert_called_once_with({2006: [snapshot_player(year=2006)]}, "afl_tables")


def test_interrupted_profile_scrape_retains_each_validated_profile(
    monkeypatch, tmp_path
):
    class Page:
        def goto(self, _url):
            return object()

        def close(self):
            pass

    class Browser:
        def new_page(self):
            return Page()

    class Source:
        def get_player_page_url(self, player_id):
            return f"https://example.test/{player_id}"

        def validate_player_navigation(self, _page, _response, _url):
            pass

        def scrape_player(self, _page, player_id, output_dir):
            if player_id == "Second_Player":
                raise RuntimeError("interrupted")
            path = output_dir / f"{player_id}.html"
            path.write_text("<h1>First Player</h1><p>1-Jan-1980</p>")
            return path

    @contextmanager
    def browser_context(_headless):
        yield Browser()

    monkeypatch.setattr(historical_players, "RAW_ROOT", tmp_path)
    monkeypatch.setattr(historical_players, "sync_browser_context", browser_context)
    monkeypatch.setattr(
        historical_players.PlayerSourceFactory, "get", Mock(return_value=Source())
    )

    with pytest.raises(RuntimeError, match="interrupted"):
        historical_players._fetch_profiles(
            ["First_Player", "Second_Player"],
            refresh=False,
            delay_ms=0,
            headless=True,
        )

    assert (tmp_path / "player" / "First_Player.html").exists()
    assert not (tmp_path / "player" / "Second_Player.html").exists()


def test_invalid_profile_cache_fails_closed_without_live_refresh(monkeypatch, tmp_path):
    monkeypatch.setattr(historical_players, "RAW_ROOT", tmp_path)
    profile = tmp_path / "player" / "Alex_Smith.html"
    profile.parent.mkdir(parents=True)
    profile.write_text("not a player page")

    with pytest.raises(ValueError, match="Invalid cached AFL Tables profile"):
        historical_players._inspect_profiles(
            {"Alex_Smith"}, refresh=False, offline=False
        )


def test_dry_run_preflights_without_opening_database(monkeypatch):
    snapshots = {2006: [snapshot_player()]}
    player = database_player()
    monkeypatch.setattr(
        historical_players,
        "_load_or_find_missing_snapshots",
        Mock(return_value=(snapshots, [])),
    )
    monkeypatch.setattr(
        historical_players,
        "_inspect_profiles",
        Mock(return_value=({player.id: player}, [])),
    )
    open_pool = Mock()
    monkeypatch.setattr(historical_players, "admin_connection_pool", open_pool)

    report = historical_players.prepare_historical_players(2006, 2006)

    assert report.dry_run is True
    assert report.unique_players == 1
    assert report.reused_profiles == 1
    open_pool.assert_not_called()


def test_load_upserts_every_preflighted_player_in_one_transaction(monkeypatch):
    snapshots = {
        2006: [snapshot_player("Alex_Smith")],
        2007: [snapshot_player("Alex_Smith", year=2007)],
    }
    player = database_player()
    monkeypatch.setattr(
        historical_players,
        "_load_or_find_missing_snapshots",
        Mock(return_value=(snapshots, [])),
    )
    monkeypatch.setattr(
        historical_players,
        "_inspect_profiles",
        Mock(return_value=({player.id: player}, [])),
    )
    connection = MagicMock()

    @contextmanager
    def pool():
        yield connection

    save = Mock(return_value=SaveResult(True, {"id": player.id}))
    monkeypatch.setattr(historical_players, "admin_connection_pool", pool)
    monkeypatch.setattr(historical_players, "save_model", save)

    report = historical_players.prepare_historical_players(2006, 2007, load=True)

    assert report.inserted_players == 1
    assert report.updated_players == 0
    save.assert_called_once_with(connection, player)
    connection.transaction.assert_called_once_with()


def test_player_model_has_database_upsert_metadata():
    player = database_player()

    assert player.__table_name__ == "player"
    assert player.__conflict_cols__ == ["id"]


def test_cli_reports_preparation_counts(monkeypatch):
    report = historical_players.HistoricalPlayerPreparationReport(
        start_year=2006,
        end_year=2011,
        snapshots=6,
        unique_players=800,
        downloaded_profiles=750,
        reused_profiles=50,
        dry_run=True,
    )
    prepare = Mock(return_value=report)
    monkeypatch.setattr(pipelines_package, "prepare_historical_players", prepare)

    result = CliRunner().invoke(
        cli_module.cli,
        ["pipeline", "prepare-historical-players", "--offline"],
    )

    assert result.exit_code == 0, result.output
    assert "Prepared 800 unique AFL Tables players" in result.output
    assert "downloaded: 750; reused: 50" in result.output
    assert prepare.call_args == call(
        2006,
        2011,
        load=False,
        refresh=False,
        offline=True,
        headless=True,
        delay_ms=500,
        progress=ANY,
    )
