from ..storage.connection import admin_connection_pool, connection_pool


def _database_version(connection) -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT version();")
        row = cursor.fetchone()
    if row is None or not row[0]:
        raise RuntimeError("PostgreSQL version query returned no value")
    return row[0]


def connection_check():
    """Connect with app credentials and return the PostgreSQL version."""
    with connection_pool() as connection:
        return _database_version(connection)


def test_admin_connection():
    """
    Test the admin connection pool (write access) by connecting and executing a query.

    Returns:
        dict: Dictionary containing connection status and database version
    """
    try:
        with admin_connection_pool() as conn:
            return {
                "status": "success",
                "connection_type": "admin (write access)",
                "version": _database_version(conn),
            }

    except Exception as e:
        return {
            "status": "error",
            "connection_type": "admin (write access)",
            "error": str(e),
        }


def test_app_connection():
    """
    Test the app connection pool (read-only access) by connecting and executing a query.

    Returns:
        dict: Dictionary containing connection status and database version
    """
    try:
        with connection_pool() as conn:
            return {
                "status": "success",
                "connection_type": "app (read-only access)",
                "version": _database_version(conn),
            }

    except Exception as e:
        return {
            "status": "error",
            "connection_type": "app (read-only access)",
            "error": str(e),
        }


def test_all_connections():
    """
    Test both admin and app connection pools.

    Returns:
        dict: Dictionary containing results for both connection types
    """
    return {
        "admin_connection": test_admin_connection(),
        "app_connection": test_app_connection(),
    }
