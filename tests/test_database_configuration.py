"""Database connection configuration contracts."""

import pytest

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

    assert get_read_conninfo() == (
        "postgresql://aflscraper_app:app-secret"
        "@localhost:5432/aflscraper_test"
    )
