"""Tests for atomic player persistence."""

from contextlib import contextmanager
from unittest.mock import MagicMock, call, patch

import pytest

from afl_scraper.pipelines.player import players_pipeline
from afl_scraper.storage import SaveResult


def _pool_for(connection):
    @contextmanager
    def pool():
        yield connection

    return pool


@patch("afl_scraper.pipelines.player.transform_player_data")
@patch("afl_scraper.pipelines.player.save_model")
def test_all_players_are_saved_in_one_transaction(save, transform):
    players = [MagicMock(id="player-1"), MagicMock(id="player-2")]
    transform.return_value = players
    save.side_effect = [
        SaveResult(True, {"id": "player-1"}),
        SaveResult(True, {"id": "player-2"}),
    ]
    connection = MagicMock()

    with patch(
        "afl_scraper.pipelines.player.admin_connection_pool",
        _pool_for(connection),
    ):
        result = players_pipeline()

    assert result == players
    assert save.call_args_list == [
        call(connection, players[0]),
        call(connection, players[1]),
    ]
    connection.transaction.assert_called_once_with()
    transaction = connection.transaction.return_value
    transaction.__enter__.assert_called_once_with()
    transaction.__exit__.assert_called_once_with(None, None, None)
    connection.commit.assert_not_called()


@patch("afl_scraper.pipelines.player.transform_player_data")
@patch("afl_scraper.pipelines.player.save_model")
def test_player_failure_rolls_back_the_complete_batch(save, transform):
    players = [MagicMock(id="player-1"), MagicMock(id="player-2")]
    transform.return_value = players
    failure = RuntimeError("player write failed")
    save.side_effect = [SaveResult(True, {"id": "player-1"}), failure]
    connection = MagicMock()

    with patch(
        "afl_scraper.pipelines.player.admin_connection_pool",
        _pool_for(connection),
    ):
        with pytest.raises(RuntimeError, match="player write failed"):
            players_pipeline()

    transaction = connection.transaction.return_value
    exit_args = transaction.__exit__.call_args.args
    assert exit_args[0] is RuntimeError
    assert exit_args[1] is failure
    connection.commit.assert_not_called()
