"""Database connection configuration contracts."""

import pytest
from click.testing import CliRunner
from psycopg.conninfo import conninfo_to_dict

from afl_scraper import cli as cli_module
from afl_scraper.storage.db_config import get_read_conninfo, get_write_conninfo


@pytest.mark.parametrize(
    ("factory", "access", "role_variables"),
    [
        (get_read_conninfo, "app", ("DB_USER_APP", "DB_PASSWORD_APP")),
        (
            get_write_conninfo,
            "owner",
            ("DB_USER_OWNER", "DB_PASSWORD_OWNER"),
        ),
    ],
)
def test_connection_configuration_fails_once_with_all_missing_variables(
    monkeypatch, factory, access, role_variables
):
    variables = ("DB_HOST", "DB_PORT", "DB_NAME", *role_variables)
    for name in variables:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValueError) as error:
        factory()

    message = str(error.value)
    assert f"for {access} access" in message
    assert "DB_HOST" in message
    assert "DB_NAME" in message
    assert role_variables[0] in message
    assert role_variables[1] in message
    assert "DB_PORT" not in message
    assert "None" not in message


def test_read_connection_uses_app_credentials_and_default_port(monkeypatch):
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_NAME", "aflscraper_test")
    monkeypatch.setenv("DB_USER_APP", "aflscraper_app")
    monkeypatch.setenv("DB_PASSWORD_APP", "app-secret")
    monkeypatch.delenv("DB_PORT", raising=False)

    assert conninfo_to_dict(get_read_conninfo()) == {
        "host": "localhost",
        "port": "5432",
        "dbname": "aflscraper_test",
        "user": "aflscraper_app",
        "password": "app-secret",
    }


def test_connection_info_preserves_reserved_password_characters(monkeypatch):
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_NAME", "aflscraper_test")
    monkeypatch.setenv("DB_USER_OWNER", "aflscraper_owner")
    monkeypatch.setenv("DB_PASSWORD_OWNER", "p@ss:word/with%spaces here")

    assert conninfo_to_dict(get_write_conninfo())["password"] == (
        "p@ss:word/with%spaces here"
    )


def test_dbcheck_exits_nonzero_when_either_connection_fails(monkeypatch):
    monkeypatch.setattr(
        cli_module,
        "test_all_connections",
        lambda: {
            "admin_connection": {
                "status": "success",
                "connection_type": "admin (write access)",
                "version": "PostgreSQL test",
            },
            "app_connection": {
                "status": "error",
                "connection_type": "app (read-only access)",
                "error": "connection refused",
            },
        },
    )

    result = CliRunner().invoke(cli_module.cli, ["dbcheck"])

    assert result.exit_code != 0
    assert "admin (write access): PostgreSQL test" in result.output
    assert "app (read-only access): connection refused" in result.output
    assert "database connection check failed" in result.output


def test_dbcheck_missing_configuration_is_a_failed_gate(monkeypatch):
    for name in (
        "DB_HOST",
        "DB_NAME",
        "DB_USER_OWNER",
        "DB_PASSWORD_OWNER",
        "DB_USER_APP",
        "DB_PASSWORD_APP",
    ):
        monkeypatch.delenv(name, raising=False)

    result = CliRunner().invoke(cli_module.cli, ["dbcheck"])

    assert result.exit_code != 0
    assert "DB_NAME" in result.output
    assert "database connection check failed" in result.output


def test_dbcheck_succeeds_only_when_both_connections_pass(monkeypatch):
    monkeypatch.setattr(
        cli_module,
        "test_all_connections",
        lambda: {
            "admin_connection": {
                "status": "success",
                "connection_type": "admin (write access)",
                "version": "PostgreSQL owner",
            },
            "app_connection": {
                "status": "success",
                "connection_type": "app (read-only access)",
                "version": "PostgreSQL app",
            },
        },
    )

    result = CliRunner().invoke(cli_module.cli, ["dbcheck"])

    assert result.exit_code == 0
    assert "PostgreSQL owner" in result.output
    assert "PostgreSQL app" in result.output
