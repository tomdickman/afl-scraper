from contextlib import contextmanager
from psycopg_pool import ConnectionPool

from afl_scraper.storage.db_config import get_admin_conninfo, get_app_conninfo


@contextmanager
def admin_connection_pool():
    pool = ConnectionPool(conninfo=get_admin_conninfo())
    try:
        with pool.connection() as conn:
            yield conn
    finally:
        pool.close()


@contextmanager
def connection_pool():
    pool = ConnectionPool(conninfo=get_app_conninfo())
    try:
        with pool.connection() as conn:
            yield conn
    finally:
        pool.close()
