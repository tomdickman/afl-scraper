"""Unit tests for generic model UPSERT persistence."""

from datetime import datetime

from unittest.mock import MagicMock

from psycopg import sql

from afl_scraper.models import DBModel, Player, PlayerGameStats
from afl_scraper.storage.save_model import (
    SaveResult,
    build_upsert_from_model,
    save_model,
)


class MockPlayer(DBModel):
    __table_name__ = "player"
    __conflict_cols__ = ["id"]
    __exclude_updates_cols__ = ["created_at"]

    id: int
    name: str
    team: str
    created_at: str


class MockPlayerStats(DBModel):
    __table_name__ = "player_game_stats"
    __conflict_cols__ = ["player_id", "game_id"]
    __exclude_updates_cols__ = []

    player_id: str
    game_id: int
    kicks: int


def _connection_with_result(result: tuple) -> tuple[MagicMock, MagicMock]:
    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.return_value = result
    return connection, cursor


class TestBuildUpsertFromModel:
    def test_build_upsert_query_and_values(self):
        model = MockPlayer(
            id=1, name="John Smith", team="Carlton", created_at="2024-01-01"
        )

        query, values = build_upsert_from_model(model)

        assert isinstance(query, sql.Composable)
        assert values == [1, "John Smith", "Carlton", "2024-01-01"]

    def test_player_stats_conflict_identity_is_player_and_game(self):
        model = MockPlayerStats(player_id="player-1", game_id=42, kicks=10)

        query, _ = build_upsert_from_model(model)
        rendered = query.as_string()

        assert 'ON CONFLICT ("player_id", "game_id")' in rendered
        assert '"kicks" = EXCLUDED."kicks"' in rendered

    def test_real_player_model_builds_idempotent_upsert(self):
        model = Player(
            id="Alex_Smith",
            givenname="Alex",
            familyname="Smith",
            birthdate=datetime(1980, 1, 1),
        )

        query, values = build_upsert_from_model(model)
        rendered = query.as_string()

        assert 'INSERT INTO "player"' in rendered
        assert 'ON CONFLICT ("id")' in rendered
        assert '"givenname" = EXCLUDED."givenname"' in rendered
        assert values == [
            "Alex_Smith",
            "Alex",
            "Smith",
            datetime(1980, 1, 1),
        ]

    def test_player_stats_replay_does_not_erase_unavailable_historical_fields(self):
        model = PlayerGameStats(
            player_id="player-1",
            team="Carlton",
            jumper_number=1,
            kicks=10,
            marks=2,
            handballs=8,
            goals=0,
            behinds=0,
            hitouts=0,
            tackles=3,
            rebound_50s=None,
            inside_50s=None,
            clearances=1,
            clangers=None,
            free_kicks_for=None,
            free_kicks_against=None,
            contested_possessions=None,
            uncontested_possessions=None,
            contested_marks=None,
            marks_inside_50=None,
            one_percenters=None,
            bounces=None,
            goal_assists=0,
            time_on_ground_percent=80,
            fantasy_points=60,
            game_id=42,
        )

        query, _ = build_upsert_from_model(model)
        rendered = query.as_string()

        assert '"kicks" = EXCLUDED."kicks"' in rendered
        assert (
            '"rebound_50s" = COALESCE(EXCLUDED."rebound_50s", '
            '"player_game_stats"."rebound_50s")' in rendered
        )
        assert (
            '"contested_possessions" = COALESCE(EXCLUDED."contested_possessions", '
            '"player_game_stats"."contested_possessions")' in rendered
        )
        for column in (
            "clearances",
            "goal_assists",
            "time_on_ground_percent",
            "fantasy_points",
        ):
            assert (
                f'"{column}" = COALESCE(EXCLUDED."{column}", '
                f'"player_game_stats"."{column}")' in rendered
            )


class TestSaveModel:
    def test_returns_single_column_identity(self):
        connection, _ = _connection_with_result((123, True))
        model = MockPlayer(
            id=123, name="Test Player", team="Adelaide", created_at="2024-03-01"
        )

        result = save_model(connection, model)

        assert result == SaveResult(was_inserted=True, identity={"id": 123})

    def test_returns_composite_identity_for_insert_and_update(self):
        connection, cursor = _connection_with_result(("player-1", 42, True))
        model = MockPlayerStats(player_id="player-1", game_id=42, kicks=10)

        inserted = save_model(connection, model)
        cursor.fetchone.return_value = ("player-1", 42, False)
        updated = save_model(connection, model.model_copy(update={"kicks": 14}))

        assert inserted == SaveResult(
            was_inserted=True,
            identity={"player_id": "player-1", "game_id": 42},
        )
        assert updated == SaveResult(
            was_inserted=False,
            identity={"player_id": "player-1", "game_id": 42},
        )

    def test_executes_query_with_values_without_committing(self):
        connection, cursor = _connection_with_result((1, True))
        model = MockPlayer(id=1, name="Test", team="Test Team", created_at="2024-01-01")

        save_model(connection, model)

        query, values = cursor.execute.call_args.args
        assert isinstance(query, sql.Composable)
        assert values == [1, "Test", "Test Team", "2024-01-01"]
        connection.commit.assert_not_called()

    def test_raises_when_upsert_returns_no_row(self):
        connection, cursor = _connection_with_result((1, True))
        cursor.fetchone.return_value = None
        model = MockPlayer(id=1, name="Test", team="Test Team", created_at="2024-01-01")

        try:
            save_model(connection, model)
        except RuntimeError as error:
            assert "returned no row" in str(error)
        else:
            raise AssertionError("Expected save_model to reject an empty RETURNING row")
