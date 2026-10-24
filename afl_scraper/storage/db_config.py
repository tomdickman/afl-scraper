import os

from psycopg.conninfo import make_conninfo


def _required_database_values(
    access: str,
    user_variable: str,
    password_variable: str,
) -> dict[str, str]:
    variables = {
        "DB_HOST": os.environ.get("DB_HOST"),
        "DB_PORT": os.environ.get("DB_PORT", "5432"),
        "DB_NAME": os.environ.get("DB_NAME"),
        user_variable: os.environ.get(user_variable),
        password_variable: os.environ.get(password_variable),
    }
    missing = sorted(name for name, value in variables.items() if not value)
    if missing:
        raise ValueError(
            f"Missing required database environment variables for {access} access: "
            + ", ".join(missing)
        )
    return {name: value for name, value in variables.items() if value is not None}


def _database_config(
    access: str,
    user_variable: str,
    password_variable: str,
) -> dict[str, str]:
    values = _required_database_values(access, user_variable, password_variable)
    return {
        "host": values["DB_HOST"],
        "port": values["DB_PORT"],
        "dbname": values["DB_NAME"],
        "user": values[user_variable],
        "password": values[password_variable],
    }


def get_write_db_config() -> dict[str, str]:
    """Return validated owner/write connection parameters."""
    return _database_config("owner", "DB_USER_OWNER", "DB_PASSWORD_OWNER")


def get_read_db_config() -> dict[str, str]:
    """Return validated app/read connection parameters."""
    return _database_config("app", "DB_USER_APP", "DB_PASSWORD_APP")


def get_write_conninfo() -> str:
    """
    Get the connection string for owner access (write access).

    Returns
    -------
        str
            PostgreSQL connection string for admin user
    """
    return make_conninfo(**get_write_db_config())


def get_read_conninfo() -> str:
    """
    Get the connection string for app/consumer access (read-only access).

    Returns
    -------
        str
            PostgreSQL connection string for app user
    """
    return make_conninfo(**get_read_db_config())


def get_db_config() -> dict:
    """
    Get database configuration as a dictionary.

    Returns
    -------
        dict
            Dictionary containing database connection parameters
    """
    return get_read_db_config()
