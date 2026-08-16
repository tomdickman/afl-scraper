from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from afl_scraper import cli as cli_module
from afl_scraper.storage.reset import (
    DevelopmentDatabaseTarget,
    get_development_database_target,
    reset_public_schema,
)


@pytest.fixture
def database_environment(monkeypatch):
    values = {
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "aflscraper_test",
        "DB_USER_OWNER": "aflscraper_owner",
        "DB_PASSWORD_OWNER": "secret",
        "DB_USER_APP": "aflscraper_app",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


@pytest.mark.parametrize("host", ["database.example.com", "::1"])
def test_reset_target_rejects_unsupported_host(database_environment, monkeypatch, host):
    monkeypatch.setenv("DB_HOST", host)

    with pytest.raises(ValueError, match="restricted to local hosts"):
        get_development_database_target()


def test_reset_target_rejects_system_database(database_environment, monkeypatch):
    monkeypatch.setenv("DB_NAME", "postgres")

    with pytest.raises(ValueError, match="system database"):
        get_development_database_target()


def test_reset_target_requires_complete_configuration(monkeypatch):
    for name in (
        "DB_HOST",
        "DB_NAME",
        "DB_USER_OWNER",
        "DB_PASSWORD_OWNER",
        "DB_USER_APP",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValueError, match="DB_HOST"):
        get_development_database_target()


def test_reset_public_schema_restores_restricted_app_access(monkeypatch):
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = (
        "aflscraper_test",
        "aflscraper_owner",
    )
    connection.transaction.return_value.__enter__ = Mock()
    connection.transaction.return_value.__exit__ = Mock(return_value=False)
    pool_context = Mock()
    pool_context.__enter__ = Mock(return_value=connection)
    pool_context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(
        "afl_scraper.storage.reset.admin_connection_pool", lambda: pool_context
    )
    target = DevelopmentDatabaseTarget(
        host="localhost",
        port="5432",
        name="aflscraper_test",
        owner="aflscraper_owner",
        app_user="aflscraper_app",
    )

    reset_public_schema(target)

    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert statements[:4] == [
        "SELECT current_database(), current_user",
        "DROP SCHEMA public CASCADE",
        "CREATE SCHEMA public",
        "REVOKE ALL ON SCHEMA public FROM PUBLIC",
    ]
    assert len(statements) == 6


def test_reset_public_schema_checks_connection_identity_before_drop(monkeypatch):
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = (
        "some_other_database",
        "aflscraper_owner",
    )
    connection.transaction.return_value.__enter__ = Mock()
    connection.transaction.return_value.__exit__ = Mock(return_value=False)
    pool_context = Mock()
    pool_context.__enter__ = Mock(return_value=connection)
    pool_context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(
        "afl_scraper.storage.reset.admin_connection_pool", lambda: pool_context
    )
    target = DevelopmentDatabaseTarget(
        host="localhost",
        port="5432",
        name="aflscraper_test",
        owner="aflscraper_owner",
        app_user="aflscraper_app",
    )

    with pytest.raises(RuntimeError, match="does not match"):
        reset_public_schema(target)

    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert statements == ["SELECT current_database(), current_user"]


def test_cli_reset_requires_exact_database_confirmation(
    database_environment, monkeypatch
):
    reset = Mock()
    monkeypatch.setattr("afl_scraper.storage.reset.reset_public_schema", reset)

    result = CliRunner().invoke(
        cli_module.cli,
        ["database", "reset", "--confirm-database", "wrong"],
    )

    assert result.exit_code != 0
    assert "confirmation did not match" in result.output
    reset.assert_not_called()


def test_cli_reset_clears_and_migrates(database_environment, monkeypatch):
    reset = Mock()
    migrate = Mock()
    monkeypatch.setattr("afl_scraper.storage.reset.reset_public_schema", reset)
    monkeypatch.setattr("afl_scraper.storage.reset.upgrade_database_to_head", migrate)

    result = CliRunner().invoke(
        cli_module.cli,
        ["database", "reset", "--confirm-database", "aflscraper_test"],
    )

    assert result.exit_code == 0, result.output
    reset.assert_called_once()
    migrate.assert_called_once_with()
    assert "Rebuilt database schema at Alembic head" in result.output


def test_cli_reset_can_leave_database_empty(database_environment, monkeypatch):
    reset = Mock()
    migrate = Mock()
    monkeypatch.setattr("afl_scraper.storage.reset.reset_public_schema", reset)
    monkeypatch.setattr("afl_scraper.storage.reset.upgrade_database_to_head", migrate)

    result = CliRunner().invoke(
        cli_module.cli,
        [
            "database",
            "reset",
            "--confirm-database",
            "aflscraper_test",
            "--no-migrate",
        ],
    )

    assert result.exit_code == 0, result.output
    reset.assert_called_once()
    migrate.assert_not_called()
    assert "left empty" in result.output
