"""
Database compatibility layer for Expense Manager.

Supports:

1. SQLite
   - Used automatically when DATABASE_URL is not set.
   - Perfect for offline/local usage.

2. PostgreSQL
   - Used automatically when DATABASE_URL is set.
   - Used by Render/Supabase in production.

The rest of the application can continue using:

    conn = db_compat.connect(DB_URL)
    cursor = conn.cursor()
    cursor.execute(...)
"""

import os
import sqlite3
import threading
from urllib.parse import urlparse


DATABASE_URL = os.getenv("DATABASE_URL")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.path.join(BASE_DIR, "expenses.db")


_pool = None
_pool_lock = threading.Lock()

def get_database_type():
    """Return the active database backend."""
    return "postgresql" if is_postgres() else "sqlite"


def column_exists(table, column):
    """
    Check whether a column exists in the active database.

    SQLite:
        Uses PRAGMA table_info().

    PostgreSQL:
        Uses information_schema.columns.
    """
    if not table or not column:
        return False

    # Only allow simple SQL identifiers here.
    # This prevents accidental SQL injection through schema helpers.
    if not table.replace("_", "").isalnum():
        raise ValueError(f"Invalid table name: {table}")

    if not column.replace("_", "").isalnum():
        raise ValueError(f"Invalid column name: {column}")

    if is_postgres():
        conn = connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                  AND column_name = %s
                LIMIT 1
                """,
                (table, column),
            )
            return cur.fetchone() is not None
        finally:
            conn.close()
    else:
        conn = connect()
        try:
            cur = conn.cursor()
            cur.execute(f"PRAGMA table_info({table})")
            columns = cur.fetchall()
            return any(row[1] == column for row in columns)
        finally:
            conn.close()



def is_postgres():
    """Return True when DATABASE_URL points to PostgreSQL."""
    if not DATABASE_URL:
        return False

    return DATABASE_URL.startswith(
        ("postgres://", "postgresql://")
    )


class SQLiteCursorWrapper:
    """
    Makes SQLite behave closer to PostgreSQL for the SQL used by this app.
    """

    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, sql, params=()):
        sql = self._convert_sql(sql)
        return self.cursor.execute(sql, params)

    def executemany(self, sql, params):
        sql = self._convert_sql(sql)
        return self.cursor.executemany(sql, params)

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def __iter__(self):
        return iter(self.cursor)

    @staticmethod
    def _convert_sql(sql):
        """
        Convert a small set of PostgreSQL syntax into SQLite syntax.
        """

        # PostgreSQL placeholders -> SQLite placeholders
        sql = sql.replace("%s", "?")

        # PostgreSQL SERIAL
        sql = sql.replace(
            "SERIAL PRIMARY KEY",
            "INTEGER PRIMARY KEY AUTOINCREMENT"
        )

        # PostgreSQL boolean-ish integer defaults
        sql = sql.replace(
            "INTEGER DEFAULT 0",
            "INTEGER DEFAULT 0"
        )

        # PostgreSQL CURRENT_TIMESTAMP is supported by SQLite,
        # so no conversion is necessary.

        # PostgreSQL CURRENT_DATE
        sql = sql.replace(
            "CURRENT_DATE",
            "date('now')"
        )

        # PostgreSQL interval syntax used by the bills page.
        sql = sql.replace(
            "date('now') + INTERVAL '7 days'",
            "date('now', '+7 days')"
        )

        # PostgreSQL date cast:
        # due_date::date
        sql = sql.replace(
            "due_date::date",
            "date(due_date)"
        )

        return sql


class SQLiteConnectionWrapper:
    """
    SQLite connection wrapper.
    """

    def __init__(self, connection):
        self.connection = connection

    def cursor(self):
        return SQLiteCursorWrapper(
            self.connection.cursor()
        )

    def commit(self):
        return self.connection.commit()

    def rollback(self):
        return self.connection.rollback()

    def close(self):
        return self.connection.close()

    def execute(self, sql, params=()):
        return SQLiteCursorWrapper(
            self.connection.cursor()
        ).execute(sql, params)

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self.connection.__exit__(
            exc_type,
            exc_value,
            traceback
        )


def _create_postgres_pool():
    """
    Lazily create a PostgreSQL connection pool.
    """

    global _pool

    if _pool is not None:
        return _pool

    with _pool_lock:
        if _pool is not None:
            return _pool

        from psycopg2 import pool

        _pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=DATABASE_URL
        )

    return _pool


class PostgresCursorWrapper:
    """
    Cursor wrapper that allows the application to continue
    using SQLite-style ? placeholders with PostgreSQL.

    Example:
        WHERE user_id=? AND status=?
    becomes:
        WHERE user_id=%s AND status=%s
    """

    def __init__(self, cursor):
        self.cursor = cursor

    @staticmethod
    def _convert_sql(sql):
        if not isinstance(sql, str):
            return sql

        return sql.replace("?", "%s")

    def execute(self, sql, params=()):
        sql = self._convert_sql(sql)
        return self.cursor.execute(sql, params)

    def executemany(self, sql, params):
        sql = self._convert_sql(sql)
        return self.cursor.executemany(sql, params)

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def fetchmany(self, size=None):
        if size is None:
            return self.cursor.fetchmany()
        return self.cursor.fetchmany(size)

    def __iter__(self):
        return iter(self.cursor)

    def __getattr__(self, name):
        return getattr(self.cursor, name)


class PostgresConnectionWrapper:
    """
    PostgreSQL pooled connection wrapper.
    """

    def __init__(self, pooled_connection, connection_pool):
        self.connection = pooled_connection
        self.pool = connection_pool

    def cursor(self):
        return PostgresCursorWrapper(
            self.connection.cursor()
        )

    def commit(self):
        return self.connection.commit()

    def rollback(self):
        return self.connection.rollback()

    def close(self):
        if self.connection is not None:
            self.pool.putconn(self.connection)
            self.connection = None

    def execute(self, sql, params=()):
        cursor = self.cursor()
        cursor.execute(sql, params)
        return cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            self.rollback()
        else:
            self.commit()

        self.close()


def connect(database=None):
    """
    Main connection function.

    Priority:

    1. Explicit PostgreSQL URL passed to connect()
    2. DATABASE_URL environment variable
    3. Local SQLite database
    """

    global DATABASE_URL

    requested_database = database or DATABASE_URL

    # PostgreSQL
    if requested_database and requested_database.startswith(
        ("postgres://", "postgresql://")
    ):
        DATABASE_URL = requested_database

        pool_instance = _create_postgres_pool()

        connection = pool_instance.getconn()

        return PostgresConnectionWrapper(
            connection,
            pool_instance
        )

    # SQLite
    sqlite_path = (
        requested_database
        if requested_database
        and not requested_database.startswith(
            ("postgres://", "postgresql://")
        )
        else SQLITE_PATH
    )

    connection = sqlite3.connect(
        sqlite_path,
        check_same_thread=False
    )

    # Important for SQLite foreign keys
    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    # Improve SQLite performance
    connection.execute(
        "PRAGMA journal_mode = WAL"
    )

    connection.execute(
        "PRAGMA synchronous = NORMAL"
    )

    connection.execute(
        "PRAGMA busy_timeout = 5000"
    )

    return SQLiteConnectionWrapper(connection)


def get_database_type():
    """
    Return the active database type.
    """

    if is_postgres():
        return "postgresql"

    return "sqlite"


def get_database_path():
    """
    Return SQLite path when SQLite is active.
    """

    if get_database_type() == "sqlite":
        return SQLITE_PATH

    return None
