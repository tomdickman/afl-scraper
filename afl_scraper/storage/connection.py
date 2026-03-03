from contextlib import contextmanager
from psycopg_pool import ConnectionPool

from ..storage.db_config import get_write_conninfo, get_read_conninfo


@contextmanager
def admin_connection_pool():
    pool = ConnectionPool(conninfo=get_write_conninfo())
    try:
        with pool.connection() as conn:
            yield conn
    finally:
        pool.close()


@contextmanager
def connection_pool():
    pool = ConnectionPool(conninfo=get_read_conninfo())
    try:
        with pool.connection() as conn:
            yield conn
    finally:
        pool.close()
