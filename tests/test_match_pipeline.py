"""Tests for atomic match persistence and official-ID mapping."""

from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

import pytest

from afl_scraper.models import Game, PlayerGameStats
from afl_scraper.pipelines.match import load_match_data
from afl_scraper.scraper.models import RawMatchData, RawMatchDetails, RawPlayerStat
from afl_scraper.storage import SaveResult


def _raw_match():
    def stat(official_id, name):
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

    return RawMatchData(
        details=RawMatchDetails(
            home_team="Carlton",
            away_team="Collingwood",
            round="Round 1",
            date="Saturday 21 September 2024",
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
        home_team_stats=[stat("101", "Player A")],
        away_team_stats=[stat("102", "Player B")],
    )


def _transformed_match():
    game = MagicMock(spec=Game)
    game.id = 42
    stats = [MagicMock(spec=PlayerGameStats), MagicMock(spec=PlayerGameStats)]
    stats[0].player_id, stats[0].game_id = "player-1", 42
    stats[1].player_id, stats[1].game_id = "player-2", 42
    return game, stats


def _pool_for(connection):
    @contextmanager
    def pool():
        yield connection

    return pool


def _connection_with_mappings(rows=(("101", "player-1"), ("102", "player-2"))):
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = list(rows)
    return connection, cursor


@patch("afl_scraper.pipelines.match.transform_match")
@patch("afl_scraper.pipelines.match.save_model")
def test_match_and_all_stats_are_saved_in_one_transaction(save, transform):
    game, stats = _transformed_match()
    transform.return_value = game, stats
    save.side_effect = [
        SaveResult(True, {"id": 42}),
        SaveResult(True, {"player_id": "player-1", "game_id": 42}),
        SaveResult(True, {"player_id": "player-2", "game_id": 42}),
    ]
    connection, cursor = _connection_with_mappings()

    with (
        patch(
            "afl_scraper.pipelines.match.admin_connection_pool",
            _pool_for(connection),
        ),
        patch(
            "afl_scraper.pipelines.match.allocate_game_id",
            return_value=(42, True),
        ) as allocate,
        patch("afl_scraper.pipelines.match.save_game_source_identity") as save_identity,
    ):
        result = load_match_data(_raw_match(), 42)

    assert result == {"game": game, "player_stats": stats}
    assert save.call_args_list == [
        call(connection, game),
        call(connection, stats[0]),
        call(connection, stats[1]),
    ]
    cursor.execute.assert_called_once()
    assert cursor.execute.call_args.args[1] == {
        "source": "afl_official",
        "year": 2024,
        "source_player_ids": ["101", "102"],
    }
    allocate.assert_called_once_with(connection, "afl_official", "42")
    save_identity.assert_called_once_with(connection, "afl_official", "42", 42)
    resolver = transform.call_args.kwargs["resolve_player_id"]
    assert resolver(_raw_match().home_team_stats[0], "Carlton", 2024) == "player-1"
    connection.transaction.assert_called_once_with()
    transaction = connection.transaction.return_value
    transaction.__enter__.assert_called_once_with()
    transaction.__exit__.assert_called_once_with(None, None, None)
    connection.commit.assert_not_called()


@patch("afl_scraper.pipelines.match.transform_match")
@patch("afl_scraper.pipelines.match.save_model")
def test_stat_failure_escapes_transaction_and_cannot_partially_commit(save, transform):
    game, stats = _transformed_match()
    transform.return_value = game, stats
    failure = RuntimeError("stat write failed")
    save.side_effect = [SaveResult(True, {"id": 42}), failure]
    connection, _ = _connection_with_mappings()

    with (
        patch(
            "afl_scraper.pipelines.match.admin_connection_pool",
            _pool_for(connection),
        ),
        patch(
            "afl_scraper.pipelines.match.allocate_game_id",
            return_value=(42, True),
        ),
        patch("afl_scraper.pipelines.match.save_game_source_identity"),
    ):
        with pytest.raises(RuntimeError, match="stat write failed"):
            load_match_data(_raw_match(), 42)

    transaction = connection.transaction.return_value
    exit_args = transaction.__exit__.call_args.args
    assert exit_args[0] is RuntimeError
    assert exit_args[1] is failure
    connection.commit.assert_not_called()


@patch("afl_scraper.pipelines.match.transform_match")
@patch("afl_scraper.pipelines.match.save_model")
def test_missing_official_id_mapping_fails_before_any_write(save, transform):
    connection, _ = _connection_with_mappings((("101", "player-1"),))

    with patch(
        "afl_scraper.pipelines.match.admin_connection_pool", _pool_for(connection)
    ):
        with pytest.raises(ValueError, match="Missing 1.*102"):
            load_match_data(_raw_match(), 42)

    transform.assert_not_called()
    save.assert_not_called()
