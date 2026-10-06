import os


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


def get_write_conninfo() -> str:
    """
    Get the connection string for owner access (write access).

    Returns
    -------
        str
            PostgreSQL connection string for admin user
    """
    values = _required_database_values(
        "owner", "DB_USER_OWNER", "DB_PASSWORD_OWNER"
    )

    return (
        f"postgresql://{values['DB_USER_OWNER']}:{values['DB_PASSWORD_OWNER']}"
        f"@{values['DB_HOST']}:{values['DB_PORT']}/{values['DB_NAME']}"
    )


def get_read_conninfo() -> str:
    """
    Get the connection string for app/consumer access (read-only access).

    Returns
    -------
        str
            PostgreSQL connection string for app user
    """
    values = _required_database_values("app", "DB_USER_APP", "DB_PASSWORD_APP")

    return (
        f"postgresql://{values['DB_USER_APP']}:{values['DB_PASSWORD_APP']}"
        f"@{values['DB_HOST']}:{values['DB_PORT']}/{values['DB_NAME']}"
    )


def get_db_config() -> dict:
    """
    Get database configuration as a dictionary.

    Returns
    -------
        dict
            Dictionary containing database connection parameters
    """
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": os.environ.get("DB_PORT", "5432"),
        "dbname": os.environ.get("DB_NAME"),
        "user": os.environ.get("DB_USER_APP"),
        "password": os.environ.get("DB_PASSWORD_APP"),
    }
