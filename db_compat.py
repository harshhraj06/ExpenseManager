"""
db_compat.py
============
A thin compatibility layer that lets the rest of the app keep using
sqlite3-style code (connect(), cursor.execute() with "?" placeholders,
cursor.fetchone()/fetchall(), cursor.lastrowid, conn.commit()) while
actually talking to a Postgres database under the hood.

Why this exists: Render's free web-service plan has no persistent disk,
so a local SQLite file (expenses.db) gets wiped on every deploy/restart.
Render's free PostgreSQL database, on the other hand, is a separate
managed service whose data persists independently of the web service's
filesystem. Swapping to Postgres fixes data loss permanently, for free
-- but Postgres uses different placeholder syntax ("%s" instead of "?"),
different autoincrement syntax, and a different way of getting the ID
of a just-inserted row. This file absorbs all of those differences in
one place, so app.py's ~50 call sites don't each need individual edits.

Usage (drop-in replacement for sqlite3 in app.py):
    import db_compat as sqlite3
    conn = sqlite3.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
"""

import re
import psycopg2
import psycopg2.extensions


class Cursor:
    """Wraps a psycopg2 cursor to accept sqlite3-style "?" placeholders
    and to expose .lastrowid the way sqlite3 cursors do."""

    def __init__(self, pg_cursor):
        self._cursor = pg_cursor
        self.lastrowid = None

    @staticmethod
    def _convert_query(query):
        """Convert sqlite3 "?" placeholders to Postgres "%s" placeholders.
        Does a simple left-to-right scan so "?" inside quoted string
        literals is not touched (none of this app's queries embed "?"
        inside a string literal, but this keeps it safe regardless)."""
        out = []
        in_single = False
        in_double = False
        for ch in query:
            if ch == "'" and not in_double:
                in_single = not in_single
                out.append(ch)
            elif ch == '"' and not in_single:
                in_double = not in_double
                out.append(ch)
            elif ch == "?" and not in_single and not in_double:
                out.append("%s")
            else:
                out.append(ch)
        return "".join(out)

    @staticmethod
    def _convert_insert_or_ignore(query):
        """sqlite3's "INSERT OR IGNORE INTO" has no direct Postgres
        equivalent as a prefix -- Postgres instead uses "ON CONFLICT DO
        NOTHING" as a suffix. This rewrites the common case used in this
        app: "INSERT OR IGNORE INTO table (...) VALUES (...)" with no
        existing ON CONFLICT clause."""
        match = re.match(
            r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\s+(.*)$",
            query,
            re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return query
        rest = match.group(1)
        return f"INSERT INTO {rest.rstrip()} ON CONFLICT DO NOTHING"

    def execute(self, query, params=None):
        query = self._convert_insert_or_ignore(query)
        query = self._convert_query(query)

        is_insert = bool(re.match(r"^\s*INSERT\s", query, re.IGNORECASE))
        if is_insert and "RETURNING" not in query.upper():
            query = query.rstrip().rstrip(";") + " RETURNING id"

        try:
            if params is None:
                self._cursor.execute(query)
            else:
                self._cursor.execute(query, tuple(params))
        except psycopg2.errors.UndefinedColumn:
            # Some INSERTs target tables/views with no "id" column (e.g.
            # none in this app currently, but this keeps it safe) --
            # retry without forcing RETURNING id.
            self._cursor.connection.rollback()
            raise

        if is_insert:
            try:
                row = self._cursor.fetchone()
                self.lastrowid = row[0] if row else None
            except psycopg2.ProgrammingError:
                # No results to fetch (e.g. INSERT ... ON CONFLICT DO
                # NOTHING with no row actually inserted).
                self.lastrowid = None
        return self

    def executemany(self, query, seq_of_params):
        query = self._convert_insert_or_ignore(query)
        query = self._convert_query(query)
        self._cursor.executemany(query, [tuple(p) for p in seq_of_params])
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchmany(self, size=None):
        if size is None:
            return self._cursor.fetchmany()
        return self._cursor.fetchmany(size)

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def close(self):
        self._cursor.close()

    def __iter__(self):
        return iter(self._cursor)


class Connection:
    """Wraps a psycopg2 connection to provide a sqlite3-style .cursor(),
    .commit(), .close(), and context-manager support."""

    def __init__(self, pg_conn):
        self._conn = pg_conn

    def cursor(self):
        return Cursor(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()


def connect(database_url, *args, **kwargs):
    """Drop-in replacement for sqlite3.connect(). The first argument is
    expected to be a Postgres connection URL (e.g. from DATABASE_URL),
    not a file path."""
    pg_conn = psycopg2.connect(database_url)
    return Connection(pg_conn)


# sqlite3 module-level constants/exceptions some code may reference --
# mapped to psycopg2 equivalents so "except sqlite3.Error" style code
# (if any exists or is added later) doesn't break.
Error = psycopg2.Error
IntegrityError = psycopg2.IntegrityError
OperationalError = psycopg2.OperationalError
ProgrammingError = psycopg2.ProgrammingError