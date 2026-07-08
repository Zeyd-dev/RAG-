"""
Metadata store for notebooks, documents, and chat history.

Two backends, selected automatically from DATABASE_URL's scheme:
- sqlite (default, "sqlite:///./data/notebook.db"): stdlib sqlite3, a
  single local file, zero accounts, zero setup -- what a fresh
  `git clone` + run gets with no configuration at all.
- Postgres ("postgresql://...", e.g. a Supabase project's connection
  string): used via psycopg2 when you want real persistent storage on a
  host whose free tier has no persistent disk (Hugging Face Spaces).
  This is opt-in only -- setting DATABASE_URL is the single switch, see
  config.py.

Router code (notebooks.py, documents.py, chat.py) is written once
against sqlite3's placeholder style ("?") and dict-like row access
(sqlite3.Row / dict(row), row["field"]). Rather than duplicate every
query for two placeholder dialects, the Postgres path wraps psycopg2 in
a thin connection/cursor shim (_PGConnection/_PGCursor below) that
translates "?" -> "%s" and returns dict-like rows via RealDictCursor --
so every existing "conn.execute(...).fetchone()/.fetchall()" call site
works unchanged against either backend.
"""
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .config import get_settings

settings = get_settings()

_QMARK_RE = re.compile(r"\?")

# Shared by both backends: plain TEXT/INTEGER columns and
# "REFERENCES ... ON DELETE CASCADE" are valid SQL in both sqlite and
# Postgres, so one schema script works unmodified for either. The
# pgvector-specific `embeddings` table (used only in Postgres mode) is
# NOT here -- it needs `CREATE EXTENSION vector`, which is a one-time
# manual step in Supabase's SQL editor, see docs/supabase_schema.sql.
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS notebooks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    notebook_id TEXT NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    page_count INTEGER,
    uploaded_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing',
    error TEXT,
    storage_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    notebook_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    page INTEGER,
    text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    notebook_id TEXT NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    citations_json TEXT,
    created_at TEXT NOT NULL
);
"""


def is_postgres() -> bool:
    return settings.DATABASE_URL.startswith("postgres")


def _db_path() -> str:
    path = settings.DATABASE_URL.replace("sqlite:///", "")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path


class _PGCursor:
    """Wraps a psycopg2 cursor so call sites written for sqlite3 --
    `.execute(sql, params).fetchone()/.fetchall()` -- work unchanged."""

    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql, params=()):
        self._cur.execute(_QMARK_RE.sub("%s", sql), params)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __getattr__(self, name):
        return getattr(self._cur, name)


class _PGConnection:
    """Wraps a psycopg2 connection so `conn.execute(...)` works directly,
    the way sqlite3.Connection allows (psycopg2's connection only has
    .cursor(), not .execute()). Rows come back dict-like via
    RealDictCursor, matching sqlite3.Row's dict(row)/row["field"] usage
    throughout the routers."""

    def __init__(self, conn):
        from psycopg2.extras import RealDictCursor

        self._conn = conn
        self._cursor_factory = RealDictCursor

    def execute(self, sql, params=()):
        cur = self._conn.cursor(cursor_factory=self._cursor_factory)
        return _PGCursor(cur).execute(sql, params)

    def executescript(self, sql):
        # Runs each ";"-separated statement in its own mini-transaction
        # instead of the whole script in one call. That's needed because
        # "CREATE TABLE IF NOT EXISTS" has a race window in Postgres: two
        # concurrent first-time startups (e.g. uvicorn --reload restarting
        # itself when it notices new __pycache__ files mid-boot, or more
        # than one app instance cold-starting against a brand new schema
        # at once) can both pass the "IF NOT EXISTS" check before either
        # has committed, then collide creating the table's implicit row
        # type in pg_catalog -- a UniqueViolation on
        # pg_type_typname_nsp_index, even though the SQL itself is
        # correct. That specific failure just means "someone else already
        # created this table," so it's swallowed per-statement rather than
        # aborting the whole script; any other kind of error still raises
        # normally.
        import psycopg2.errors

        for stmt in (s.strip() for s in sql.split(";")):
            if not stmt:
                continue
            cur = self._conn.cursor()
            try:
                cur.execute(stmt)
                self._conn.commit()
            except (
                psycopg2.errors.DuplicateTable,
                psycopg2.errors.DuplicateObject,
                psycopg2.errors.UniqueViolation,
            ):
                self._conn.rollback()

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


@contextmanager
def get_conn():
    if is_postgres():
        import psycopg2

        conn = psycopg2.connect(settings.DATABASE_URL)
        wrapped = _PGConnection(conn)
        try:
            yield wrapped
            wrapped.commit()
        finally:
            wrapped.close()
    else:
        conn = sqlite3.connect(_db_path())
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init_db() -> None:
    """Creates the metadata tables if missing. Safe to call on every
    startup against either backend (IF NOT EXISTS everywhere). Note this
    only covers notebooks/documents/chunks/chat_messages -- the pgvector
    `embeddings` table used when DATABASE_URL is Postgres is a one-time
    manual step, see docs/supabase_schema.sql, since it needs
    `CREATE EXTENSION vector`, which Supabase wants run explicitly in its
    SQL editor rather than silently from app code on every boot."""
    with get_conn() as conn:
        conn.executescript(SCHEMA_SQL)


def new_id() -> str:
    return uuid.uuid4().hex


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
