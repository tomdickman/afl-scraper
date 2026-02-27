import psycopg_pool

from afl_scraper.storage.connection import admin_connection_pool, connection_pool
from afl_scraper.storage.db_config import get_db_config


def connection_check():
    # Get database connection configuration
    db_config = get_db_config()

    if any(env_var is None for env_var in db_config.values()):
        raise EnvironmentError("Missing required environment variable")

    #  Create a connection pool
    pool = None
    version = None
    try:
        pool = psycopg_pool.ConnectionPool(
            kwargs=dict(
                dbname=db_config["dbname"],
                host=db_config["host"],
                port=int(db_config["port"]),
                user=db_config["user"],
                password=db_config["password"],
            )
        )

        try:
            with pool.connection() as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT version();")
                version = cursor.fetchone()
                cursor.close()

        except Exception as e:
            print(f"Error during database operation: {e}")

    except Exception as e:
        print(f"Error connecting to the database: {e}")

    finally:
        # Close the connection pool (important to release resources)
        if pool:  # Ensure pool is initialized before attempting to close
            pool.close()

        return version


def test_admin_connection():
    """
    Test the admin connection pool (write access) by connecting and executing a query.

    Returns:
        dict: Dictionary containing connection status and database version
    """
    try:
        with admin_connection_pool() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT version();")
            version = cursor.fetchone()
            cursor.close()

            return {
                "status": "success",
                "connection_type": "admin (write access)",
                "version": version[0] if version else None,
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
            cursor = conn.cursor()
            cursor.execute("SELECT version();")
            version = cursor.fetchone()
            cursor.close()

            return {
                "status": "success",
                "connection_type": "app (read-only access)",
                "version": version[0] if version else None,
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
