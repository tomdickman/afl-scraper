"""Tests for atomic match persistence."""

from contextlib import contextmanager
from unittest.mock import MagicMock, call, patch

import pytest

from afl_scraper.models import Game, PlayerGameStats
from afl_scraper.pipelines.match import load_match_data
from afl_scraper.storage import SaveResult


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
    connection = MagicMock()

    with patch(
        "afl_scraper.pipelines.match.admin_connection_pool",
        _pool_for(connection),
    ):
        result = load_match_data({}, 42)

    assert result == {"game": game, "player_stats": stats}
    assert save.call_args_list == [
        call(connection, game),
        call(connection, stats[0]),
        call(connection, stats[1]),
    ]
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
    connection = MagicMock()

    with patch(
        "afl_scraper.pipelines.match.admin_connection_pool",
        _pool_for(connection),
    ):
        with pytest.raises(RuntimeError, match="stat write failed"):
            load_match_data({}, 42)

    transaction = connection.transaction.return_value
    exit_args = transaction.__exit__.call_args.args
    assert exit_args[0] is RuntimeError
    assert exit_args[1] is failure
    connection.commit.assert_not_called()
