"""Unit tests for the save_model storage module."""

from unittest.mock import Mock, MagicMock
from psycopg import sql

from afl_scraper.storage.save_model import save_model, build_upsert_from_model
from afl_scraper.models import DBModel


class MockPlayer(DBModel):
    """Mock player model for testing."""

    __table_name__ = "player"
    __conflict_cols__ = ["id"]
    __exclude_updates_cols__ = ["created_at"]

    id: int
    name: str
    team: str
    created_at: str


class TestBuildUpsertFromModel:
    """Test cases for the build_upsert_from_model function."""

    def test_build_upsert_query_structure(self):
        """Test that the upsert query is built with correct structure."""
        model = MockPlayer(
            id=1, name="John Smith", team="Carlton", created_at="2024-01-01"
        )

        query, values = build_upsert_from_model(model)

        # Verify query is a SQL Composable object
        assert isinstance(query, sql.Composable)

        # Verify values match model data
        assert values == [1, "John Smith", "Carlton", "2024-01-01"]

    def test_build_upsert_values_extraction(self):
        """Test that values are correctly extracted from model."""
        model = MockPlayer(
            id=42, name="Jane Doe", team="Essendon", created_at="2024-02-15"
        )

        query, values = build_upsert_from_model(model)

        # Verify all model values are included
        assert 42 in values
        assert "Jane Doe" in values
        assert "Essendon" in values
        assert "2024-02-15" in values


class TestSaveModel:
    """Test cases for the save_model function."""

    def test_save_model_returns_tuple(self):
        """Test that save_model returns a tuple of (was_inserted, record_id)."""
        # Mock database connection and cursor
        mock_conn = Mock()
        mock_cursor = MagicMock()
        mock_conn.cursor = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(return_value=mock_cursor), __exit__=MagicMock()
            )
        )

        # Mock fetchone to return (record_id, was_inserted)
        # PostgreSQL RETURNING returns: id, (xmax = 0) AS inserted
        mock_cursor.fetchone.return_value = (123, True)

        model = MockPlayer(
            id=123, name="Test Player", team="Adelaide", created_at="2024-03-01"
        )

        result = save_model(mock_conn, model)

        # Verify return value is a tuple
        assert isinstance(result, tuple)
        assert len(result) == 2

        # Verify tuple contents (was_inserted, record_id)
        was_inserted, record_id = result
        assert was_inserted is True
        assert record_id == 123

    def test_save_model_insert_scenario(self):
        """Test save_model when a new record is inserted."""
        mock_conn = Mock()
        mock_cursor = MagicMock()
        mock_conn.cursor = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(return_value=mock_cursor), __exit__=MagicMock()
            )
        )

        # Simulate INSERT: xmax = 0 returns True
        mock_cursor.fetchone.return_value = (999, True)

        model = MockPlayer(
            id=999, name="New Player", team="Brisbane Lions", created_at="2024-04-01"
        )

        was_inserted, record_id = save_model(mock_conn, model)

        # Verify insert behavior
        assert was_inserted is True
        assert record_id == 999
        assert mock_cursor.execute.called
        assert mock_conn.commit.called

    def test_save_model_update_scenario(self):
        """Test save_model when an existing record is updated."""
        mock_conn = Mock()
        mock_cursor = MagicMock()
        mock_conn.cursor = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(return_value=mock_cursor), __exit__=MagicMock()
            )
        )

        # Simulate UPDATE: xmax > 0 returns False
        mock_cursor.fetchone.return_value = (555, False)

        model = MockPlayer(
            id=555, name="Updated Player", team="Collingwood", created_at="2024-05-01"
        )

        was_inserted, record_id = save_model(mock_conn, model)

        # Verify update behavior
        assert was_inserted is False
        assert record_id == 555
        assert mock_cursor.execute.called
        assert mock_conn.commit.called

    def test_save_model_executes_query_with_values(self):
        """Test that save_model executes query with correct values."""
        mock_conn = Mock()
        mock_cursor = MagicMock()
        mock_conn.cursor = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(return_value=mock_cursor), __exit__=MagicMock()
            )
        )
        mock_cursor.fetchone.return_value = (1, True)

        model = MockPlayer(id=1, name="Test", team="Test Team", created_at="2024-01-01")

        save_model(mock_conn, model)

        # Verify execute was called with query and values
        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args
        assert len(call_args[0]) == 2  # query and values

        # Verify values were passed
        query, values = call_args[0]
        assert isinstance(query, sql.Composable)
        assert isinstance(values, list)

    def test_save_model_commits_transaction(self):
        """Test that save_model commits the transaction."""
        mock_conn = Mock()
        mock_cursor = MagicMock()
        mock_conn.cursor = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(return_value=mock_cursor), __exit__=MagicMock()
            )
        )
        mock_cursor.fetchone.return_value = (1, True)

        model = MockPlayer(id=1, name="Test", team="Test Team", created_at="2024-01-01")

        save_model(mock_conn, model)

        # Verify commit was called
        mock_conn.commit.assert_called_once()

    def test_save_model_uses_context_manager_for_cursor(self):
        """Test that save_model properly uses context manager for cursor."""
        mock_conn = Mock()
        mock_cursor = MagicMock()
        mock_context = MagicMock(
            __enter__=MagicMock(return_value=mock_cursor), __exit__=MagicMock()
        )
        mock_conn.cursor = MagicMock(return_value=mock_context)
        mock_cursor.fetchone.return_value = (1, True)

        model = MockPlayer(id=1, name="Test", team="Test Team", created_at="2024-01-01")

        save_model(mock_conn, model)

        # Verify cursor context manager was used
        mock_context.__enter__.assert_called_once()
        mock_context.__exit__.assert_called_once()
