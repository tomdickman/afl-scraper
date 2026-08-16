"""Guarded reset support for disposable local development databases."""

import os
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from psycopg import sql

from .connection import admin_connection_pool


_LOCAL_DATABASE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_SYSTEM_DATABASES = frozenset({"postgres", "template0", "template1"})


@dataclass(frozen=True)
class DevelopmentDatabaseTarget:
    """A validated local database target safe enough to offer for reset."""

    host: str
    port: str
    name: str
    owner: str
    app_user: str


def get_development_database_target() -> DevelopmentDatabaseTarget:
    """Validate the environment and refuse targets that are not clearly local."""
    values = {
        "DB_HOST": os.environ.get("DB_HOST", "localhost").strip(),
        "DB_PORT": os.environ.get("DB_PORT", "5432").strip(),
        "DB_NAME": os.environ.get("DB_NAME", "").strip(),
        "DB_USER_OWNER": os.environ.get("DB_USER_OWNER", "").strip(),
        "DB_PASSWORD_OWNER": os.environ.get("DB_PASSWORD_OWNER", ""),
        "DB_USER_APP": os.environ.get("DB_USER_APP", "").strip(),
    }
    missing = sorted(name for name, value in values.items() if not value)
    if missing:
        raise ValueError(
            "database reset requires these environment variables: " + ", ".join(missing)
        )

    host = values["DB_HOST"].lower()
    if host not in _LOCAL_DATABASE_HOSTS:
        raise ValueError(
            f"database reset is restricted to local hosts; got DB_HOST={host!r}"
        )

    name = values["DB_NAME"]
    if name.lower() in _SYSTEM_DATABASES:
        raise ValueError(f"refusing to reset PostgreSQL system database {name!r}")

    return DevelopmentDatabaseTarget(
        host=host,
        port=values["DB_PORT"],
        name=name,
        owner=values["DB_USER_OWNER"],
        app_user=values["DB_USER_APP"],
    )


def reset_public_schema(target: DevelopmentDatabaseTarget) -> None:
    """Delete every object in public and restore the project's schema grants."""
    with admin_connection_pool() as connection:
        with connection.transaction():
            database_name, database_user = connection.execute(
                "SELECT current_database(), current_user"
            ).fetchone()
            if (database_name, database_user) != (target.name, target.owner):
                raise RuntimeError(
                    "connected database identity does not match the confirmed target"
                )
            connection.execute("DROP SCHEMA public CASCADE")
            connection.execute("CREATE SCHEMA public")
            connection.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
            connection.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                    sql.Identifier(target.app_user)
                )
            )
            connection.execute(
                sql.SQL("REVOKE CREATE ON SCHEMA public FROM {}").format(
                    sql.Identifier(target.app_user)
                )
            )


def upgrade_database_to_head() -> None:
    """Rebuild the empty schema using the checked-out Alembic migration graph."""
    config = Config()
    migrations = Path(__file__).resolve().parent / "migrations"
    config.set_main_option("script_location", str(migrations))
    command.upgrade(config, "head")
