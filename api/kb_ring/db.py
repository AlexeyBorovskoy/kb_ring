from contextlib import contextmanager

import psycopg

from .config import DATABASE_URL


@contextmanager
def db_conn():
    # Держим максимально просто/синхронно на этапе 1. Позже можно добавить пул соединений.
    conn = psycopg.connect(DATABASE_URL, autocommit=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
