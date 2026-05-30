"""Shared fixtures for tests/unit/utils/.

Adds DB isolation on top of the singleton/cache isolation already provided by
the root conftest.  The existing app_info_cache and config patches remain; this
file only adds what they don't cover.
"""

import sqlite3

import pytest

# Minimal schema covering only the tables exercised by filepath_update.py.
_MINI_SCHEMA = """
CREATE TABLE IF NOT EXISTS directories (
    path       TEXT PRIMARY KEY,
    files      TEXT NOT NULL DEFAULT '[]',
    scanned_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS media_tracks (
    filepath        TEXT PRIMARY KEY,
    parent_filepath TEXT,
    title           TEXT,
    artist          TEXT,
    album           TEXT,
    scanned_at      REAL NOT NULL
);
"""


@pytest.fixture
def isolated_db(monkeypatch):
    """Redirect utils.db.get_connection to a fresh in-memory SQLite DB.

    Prevents tests from touching the real muse_library.db on disk.
    The existing cache/config isolation from the root conftest is unchanged.
    """
    import utils.db as db_mod

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_MINI_SCHEMA)
    conn.commit()

    monkeypatch.setattr(db_mod, "get_connection", lambda: conn)
    monkeypatch.setattr(db_mod, "_connection", conn)

    yield conn
    conn.close()
