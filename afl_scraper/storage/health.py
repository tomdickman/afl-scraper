import os

import psycopg_pool

def connection_check():
    # Database connection details from environment variables
    db_host = os.environ.get("DB_HOST", "localhost")  # Default to localhost if not set
    db_name = os.environ.get("DB_NAME")
    db_user = os.environ.get("DB_USER_APP")
    db_password = os.environ.get("DB_PASSWORD_APP")
    db_port = os.environ.get("DB_PORT", "5432") # Default port is 5432

    if (any(env_var is None for env_var in [db_host, db_name, db_user, db_password, db_port])):
        raise EnvironmentError("Missing required environment variable")

    #  Create a connection pool
    try:
        conninfo = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        connection_pool = psycopg_pool.ConnectionPool(conninfo=conninfo)

        try:
            with connection_pool.connection() as connection:
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
        if connection_pool:  # Ensure pool is initialized before attempting to close
            connection_pool.close()

        return version
