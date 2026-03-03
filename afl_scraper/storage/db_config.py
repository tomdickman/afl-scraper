import os


def get_write_conninfo() -> str:
    """
    Get the connection string for owner access (write access).

    Returns
    -------
        str
            PostgreSQL connection string for admin user
    """
    db_user = os.environ.get("DB_USER_OWNER")
    db_password = os.environ.get("DB_PASSWORD_OWNER")
    db_host = os.environ.get("DB_HOST")
    db_port = os.environ.get("DB_PORT", "5432")
    db_name = os.environ.get("DB_NAME")

    return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"


def get_read_conninfo() -> str:
    """
    Get the connection string for app/consumer access (read-only access).

    Returns
    -------
        str
            PostgreSQL connection string for app user
    """
    db_user = os.environ.get("DB_USER_APP")
    db_password = os.environ.get("DB_PASSWORD_APP")
    db_host = os.environ.get("DB_HOST")
    db_port = os.environ.get("DB_PORT", "5432")
    db_name = os.environ.get("DB_NAME")

    return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"


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
