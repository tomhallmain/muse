"""
SQLite persistence layer for Muse.

Single entry point: get_connection() returns the process-wide singleton
connection to configs/muse_library.db.  The schema is created and seed data
is imported automatically on the first call; subsequent calls return the
already-open connection.

Seeding order (one-time, on fresh DB):
  1. *_example.json files  → canonical seed data for each table
  2. live *.json files      → INSERT OR IGNORE (picks up user edits not yet
                              in the example files; legacy files are preserved)
  3. gzip caches            → lastfm_cache.json.gz and musicbrainz_cache.json.gz
                              migrated once, then superseded by direct SQLite writes

Migration state is tracked in the db_meta table so each step runs exactly once.
"""

import gzip
import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "configs" / "muse_library.db"
_DATA_DIR = Path(__file__).resolve().parent.parent / "library_data" / "data"
_GZIP_LFM = Path(__file__).resolve().parent.parent / "configs" / "lastfm_cache.json.gz"
_GZIP_MB = Path(__file__).resolve().parent.parent / "configs" / "musicbrainz_cache.json.gz"

DELIM = "; "

_connection: Optional[sqlite3.Connection] = None
_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS db_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ─── Reference data ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS composers (
    id                  INTEGER PRIMARY KEY,
    name                TEXT    NOT NULL UNIQUE,
    mbid                TEXT,
    indicators          TEXT    NOT NULL DEFAULT '',
    start_date          INTEGER,
    end_date            INTEGER,
    dates_are_lifespan  INTEGER NOT NULL DEFAULT 1,
    dates_uncertain     INTEGER NOT NULL DEFAULT 0,
    genres              TEXT    NOT NULL DEFAULT '',
    works               TEXT    NOT NULL DEFAULT '',
    notes               TEXT    NOT NULL DEFAULT '{}',
    date_added          TEXT
);
CREATE INDEX IF NOT EXISTS idx_composers_name ON composers(name);

CREATE TABLE IF NOT EXISTS artists (
    id                  INTEGER,
    name                TEXT    NOT NULL UNIQUE,
    indicators          TEXT    NOT NULL DEFAULT '',
    start_date          INTEGER,
    end_date            INTEGER,
    dates_are_lifespan  INTEGER NOT NULL DEFAULT 1,
    dates_uncertain     INTEGER NOT NULL DEFAULT 0,
    genres              TEXT    NOT NULL DEFAULT '',
    albums              TEXT    NOT NULL DEFAULT '',
    notes               TEXT    NOT NULL DEFAULT '{}',
    PRIMARY KEY (name)
);
CREATE INDEX IF NOT EXISTS idx_artists_name ON artists(name);

CREATE TABLE IF NOT EXISTS forms (
    name             TEXT PRIMARY KEY,
    transliterations TEXT NOT NULL DEFAULT '',
    notes            TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS genres (
    name             TEXT PRIMARY KEY,
    transliterations TEXT NOT NULL DEFAULT '',
    notes            TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS instruments (
    name TEXT PRIMARY KEY
);

-- ─── Directory and media-track caches ───────────────────────────────────────
-- Replaces app_directories_cache (pickle) and app_media_track_cache (pickle).

CREATE TABLE IF NOT EXISTS directories (
    path       TEXT PRIMARY KEY,
    files      TEXT NOT NULL DEFAULT '[]',  -- JSON array of absolute file paths
    scanned_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS media_tracks (
    filepath         TEXT PRIMARY KEY,
    parent_filepath  TEXT,
    title            TEXT,
    tracktitle       TEXT,
    artist           TEXT,
    albumartist      TEXT,
    album            TEXT,
    composer         TEXT,
    tracknumber      INTEGER,
    totaltracks      INTEGER,
    discnumber       INTEGER,
    totaldiscs       INTEGER,
    genre            TEXT,
    year             INTEGER,
    compilation      INTEGER NOT NULL DEFAULT 0,
    compilation_name TEXT,
    mean_volume      REAL,
    max_volume       REAL,
    length           REAL,
    form             TEXT,
    instrument       TEXT,
    is_video         INTEGER,
    scanned_at       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_media_tracks_artist   ON media_tracks(artist);
CREATE INDEX IF NOT EXISTS idx_media_tracks_composer ON media_tracks(composer);
CREATE INDEX IF NOT EXISTS idx_media_tracks_album    ON media_tracks(album);

-- ─── Blacklist (populated when Blacklist class is migrated to DB) ─────────────

CREATE TABLE IF NOT EXISTS blacklist (
    pattern TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS blacklist_music (
    name    TEXT    NOT NULL,
    type    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (name, type)
);

-- ─── Last.fm library cache ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS lfm_scopes (
    username   TEXT NOT NULL,
    scope      TEXT NOT NULL,
    fetched_at REAL NOT NULL,
    PRIMARY KEY (username, scope)
);

CREATE TABLE IF NOT EXISTS lfm_tracks (
    username    TEXT    NOT NULL,
    scope       TEXT    NOT NULL DEFAULT 'tracks',
    mbid        TEXT    NOT NULL DEFAULT '',
    name        TEXT    NOT NULL,
    artist      TEXT    NOT NULL DEFAULT '',
    playcount   INTEGER NOT NULL DEFAULT 0,
    rank        INTEGER,
    album       TEXT,
    fetched_at  REAL    NOT NULL,
    PRIMARY KEY (username, scope, artist, name)
);
CREATE INDEX IF NOT EXISTS idx_lfm_tracks_username ON lfm_tracks(username);
CREATE INDEX IF NOT EXISTS idx_lfm_tracks_mbid     ON lfm_tracks(mbid) WHERE mbid != '';

-- ─── MusicBrainz enrichment cache ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS mb_recordings (
    mbid         TEXT PRIMARY KEY,
    mb_title     TEXT NOT NULL DEFAULT '',
    mb_artist    TEXT NOT NULL DEFAULT '',
    mb_genres    TEXT NOT NULL DEFAULT '',
    composer     TEXT NOT NULL DEFAULT '',
    lyricist     TEXT NOT NULL DEFAULT '',
    arranger     TEXT NOT NULL DEFAULT '',
    orchestrator TEXT NOT NULL DEFAULT '',
    writer       TEXT NOT NULL DEFAULT '',
    fetched_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mb_composer ON mb_recordings(composer);

-- ─── MusicBrainz failed-lookup cache ─────────────────────────────────────────
-- Tracks every MBID whose MusicBrainz endpoint returned a non-retriable error
-- (e.g. 404 Not Found).  Kept separate from mb_recordings so that genuinely
-- credit-free recordings are not confused with invalid or stale MBIDs.

CREATE TABLE IF NOT EXISTS mb_failed_lookups (
    mbid        TEXT PRIMARY KEY,
    endpoint    TEXT NOT NULL DEFAULT '',  -- e.g. 'recording', 'release'
    status_code INTEGER,                   -- HTTP status if available, else NULL
    failed_at   REAL NOT NULL              -- unix timestamp
);
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    """Return the process-wide singleton DB connection, initializing on first call."""
    global _connection
    with _lock:
        if _connection is None:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            _create_schema(conn)
            _seed_if_needed(conn)
            _migrate_gzip_caches(conn)
            _connection = conn
    return _connection


def list_to_delim(values) -> str:
    """Join a list of strings with DELIM.  Returns '' for empty/None input."""
    if not values:
        return ""
    return DELIM.join(str(v) for v in values)


def delim_to_list(value: str) -> List[str]:
    """Split a DELIM-joined string back into a list.  Returns [] for empty string."""
    if not value:
        return []
    return [x for x in value.split(DELIM) if x]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)


def _get_meta(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM db_meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO db_meta (key, value) VALUES (?, ?)", (key, value)
    )


# ---------------------------------------------------------------------------
# Seeding from *_example.json files
# ---------------------------------------------------------------------------

def _seed_if_needed(conn: sqlite3.Connection) -> None:
    if _get_meta(conn, "seeded") == "1":
        return
    logger.info("Fresh database — seeding from example files...")
    _seed_forms(conn)
    _seed_genres(conn)
    _seed_instruments(conn)
    _seed_composers(conn)
    _seed_artists(conn)
    _seed_blacklist(conn)
    _seed_blacklist_music(conn)
    _set_meta(conn, "seeded", "1")
    conn.commit()
    logger.info("Seed complete — migrating legacy JSON files...")
    _migrate_legacy_json(conn)
    logger.info("Legacy JSON migration complete.")


def _seed_forms(conn: sqlite3.Connection) -> None:
    path = _DATA_DIR / "forms_example.json"
    if not path.exists():
        logger.warning("forms_example.json not found, skipping")
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = [
        (v["name"], list_to_delim(v.get("transliterations", [])), json.dumps(v.get("notes", {})))
        for v in data.values()
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO forms (name, transliterations, notes) VALUES (?, ?, ?)",
        rows,
    )
    logger.debug("Seeded %d forms", len(rows))


def _seed_genres(conn: sqlite3.Connection) -> None:
    path = _DATA_DIR / "genres_example.json"
    if not path.exists():
        logger.warning("genres_example.json not found, skipping")
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = [
        (v["name"], list_to_delim(v.get("transliterations", [])), json.dumps(v.get("notes", {})))
        for v in data.values()
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO genres (name, transliterations, notes) VALUES (?, ?, ?)",
        rows,
    )
    logger.debug("Seeded %d genres", len(rows))


def _seed_instruments(conn: sqlite3.Connection) -> None:
    path = _DATA_DIR / "instruments_example.json"
    if not path.exists():
        logger.warning("instruments_example.json not found, skipping")
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    conn.executemany(
        "INSERT OR IGNORE INTO instruments (name) VALUES (?)",
        [(name,) for name in data],
    )
    logger.debug("Seeded %d instruments", len(data))


def _seed_composers(conn: sqlite3.Connection) -> None:
    path = _DATA_DIR / "composers_example.json"
    if not path.exists():
        logger.warning("composers_example.json not found, skipping")
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = [
        (
            v.get("id"),
            v.get("name"),
            v.get("mbid"),
            list_to_delim(v.get("indicators", [])),
            v.get("start_date"),
            v.get("end_date"),
            1 if v.get("dates_are_lifespan", True) else 0,
            1 if v.get("dates_uncertain", False) else 0,
            list_to_delim(v.get("genres", [])),
            list_to_delim(v.get("works", [])),
            json.dumps(v.get("notes", {})),
            v.get("date_added"),
        )
        for v in data.values()
    ]
    conn.executemany(
        """INSERT OR IGNORE INTO composers
           (id, name, mbid, indicators, start_date, end_date,
            dates_are_lifespan, dates_uncertain, genres, works, notes, date_added)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    logger.debug("Seeded %d composers", len(rows))


def _seed_artists(conn: sqlite3.Connection) -> None:
    path = _DATA_DIR / "artists_example.json"
    if not path.exists():
        logger.warning("artists_example.json not found, skipping")
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = [
        (
            v.get("id"),
            v.get("name"),
            list_to_delim(v.get("indicators", [])),
            v.get("start_date"),
            v.get("end_date"),
            1 if v.get("dates_are_lifespan", True) else 0,
            1 if v.get("dates_uncertain", False) else 0,
            list_to_delim(v.get("genres", [])),
            list_to_delim(v.get("albums", [])),
            json.dumps(v.get("notes", {})),
        )
        for v in data.values()
    ]
    conn.executemany(
        """INSERT OR IGNORE INTO artists
           (id, name, indicators, start_date, end_date,
            dates_are_lifespan, dates_uncertain, genres, albums, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    logger.debug("Seeded %d artists", len(rows))


def _seed_blacklist(conn: sqlite3.Connection) -> None:
    path = _DATA_DIR / "blacklist.json"
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    patterns = [p for p in data if isinstance(p, str)]
    conn.executemany(
        "INSERT OR IGNORE INTO blacklist (pattern) VALUES (?)",
        [(p,) for p in patterns],
    )
    logger.debug("Seeded %d blacklist patterns", len(patterns))


def _seed_blacklist_music(conn: sqlite3.Connection) -> None:
    path = _DATA_DIR / "blacklist_music.json"
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = [
        (item["name"], item.get("type", 0))
        for item in data
        if isinstance(item, dict) and "name" in item
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO blacklist_music (name, type) VALUES (?, ?)",
        rows,
    )
    logger.debug("Seeded %d blacklist_music entries", len(rows))


# ---------------------------------------------------------------------------
# Legacy JSON migration (INSERT OR IGNORE — preserves existing seed data)
# ---------------------------------------------------------------------------

def _migrate_legacy_json(conn: sqlite3.Connection) -> None:
    _migrate_legacy_forms(conn)
    _migrate_legacy_genres(conn)
    _migrate_legacy_instruments(conn)
    _migrate_legacy_composers(conn)
    _migrate_legacy_artists(conn)


def _migrate_legacy_forms(conn: sqlite3.Connection) -> None:
    path = _DATA_DIR / "forms.json"
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = [
        (v["name"], list_to_delim(v.get("transliterations", [])), json.dumps(v.get("notes", {})))
        for v in data.values()
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO forms (name, transliterations, notes) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def _migrate_legacy_genres(conn: sqlite3.Connection) -> None:
    path = _DATA_DIR / "genres.json"
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = [
        (v["name"], list_to_delim(v.get("transliterations", [])), json.dumps(v.get("notes", {})))
        for v in data.values()
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO genres (name, transliterations, notes) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def _migrate_legacy_instruments(conn: sqlite3.Connection) -> None:
    path = _DATA_DIR / "instruments.json"
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    conn.executemany(
        "INSERT OR IGNORE INTO instruments (name) VALUES (?)",
        [(name,) for name in data],
    )
    conn.commit()


def _migrate_legacy_composers(conn: sqlite3.Connection) -> None:
    import datetime
    import os

    path = _DATA_DIR / "composers.json"
    if not path.exists():
        return
    mtime_iso = datetime.datetime.fromtimestamp(os.path.getmtime(str(path))).isoformat()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = [
        (
            v.get("id"),
            v.get("name"),
            v.get("mbid"),
            list_to_delim(v.get("indicators", [])),
            v.get("start_date"),
            v.get("end_date"),
            1 if v.get("dates_are_lifespan", True) else 0,
            1 if v.get("dates_uncertain", False) else 0,
            list_to_delim(v.get("genres", [])),
            list_to_delim(v.get("works", [])),
            json.dumps(v.get("notes", {})),
            v.get("date_added") or mtime_iso,
        )
        for v in data.values()
    ]
    conn.executemany(
        """INSERT OR IGNORE INTO composers
           (id, name, mbid, indicators, start_date, end_date,
            dates_are_lifespan, dates_uncertain, genres, works, notes, date_added)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    logger.info("Legacy composer migration: %d records processed", len(rows))


def _migrate_legacy_artists(conn: sqlite3.Connection) -> None:
    path = _DATA_DIR / "artists.json"
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = [
        (
            v.get("id"),
            v.get("name"),
            list_to_delim(v.get("indicators", [])),
            v.get("start_date"),
            v.get("end_date"),
            1 if v.get("dates_are_lifespan", True) else 0,
            1 if v.get("dates_uncertain", False) else 0,
            list_to_delim(v.get("genres", [])),
            list_to_delim(v.get("albums", [])),
            json.dumps(v.get("notes", {})),
        )
        for v in data.values()
    ]
    conn.executemany(
        """INSERT OR IGNORE INTO artists
           (id, name, indicators, start_date, end_date,
            dates_are_lifespan, dates_uncertain, genres, albums, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    logger.info("Legacy artist migration: %d records processed", len(rows))


# ---------------------------------------------------------------------------
# Gzip cache migration (runs once per file, tracked via db_meta)
# ---------------------------------------------------------------------------

def _migrate_gzip_caches(conn: sqlite3.Connection) -> None:
    _migrate_gzip_mb(conn)
    _migrate_gzip_lfm(conn)


def _migrate_gzip_mb(conn: sqlite3.Connection) -> None:
    import time

    if _get_meta(conn, "gzip_mb_migrated") == "1":
        return
    if not _GZIP_MB.exists():
        _set_meta(conn, "gzip_mb_migrated", "1")
        conn.commit()
        return
    logger.info("Migrating MusicBrainz gzip cache to SQLite...")
    try:
        with gzip.open(str(_GZIP_MB), "rt", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.warning("Unexpected MB cache format; skipping migration")
            return
        now = time.time()
        rows = [
            (
                mbid,
                record.get("mb_title", ""),
                record.get("mb_artist", ""),
                list_to_delim(record.get("mb_genres", [])),
                list_to_delim(record.get("composer", [])),
                list_to_delim(record.get("lyricist", [])),
                list_to_delim(record.get("arranger", [])),
                list_to_delim(record.get("orchestrator", [])),
                list_to_delim(record.get("writer", [])),
                now,
            )
            for mbid, record in data.items()
        ]
        conn.executemany(
            """INSERT OR IGNORE INTO mb_recordings
               (mbid, mb_title, mb_artist, mb_genres, composer,
                lyricist, arranger, orchestrator, writer, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        _set_meta(conn, "gzip_mb_migrated", "1")
        conn.commit()
        logger.info("MB gzip migration complete: %d records", len(rows))
    except Exception as exc:
        logger.error("Failed to migrate MB gzip cache: %s", exc)


def _migrate_gzip_lfm(conn: sqlite3.Connection) -> None:
    import time

    if _get_meta(conn, "gzip_lfm_migrated") == "1":
        return
    if not _GZIP_LFM.exists():
        _set_meta(conn, "gzip_lfm_migrated", "1")
        conn.commit()
        return
    logger.info("Migrating Last.fm gzip cache to SQLite...")
    try:
        with gzip.open(str(_GZIP_LFM), "rt", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.warning("Unexpected LFM cache format; skipping migration")
            return
        now = time.time()
        scope_rows: List = []
        track_rows: List = []
        for username, entry in data.items():
            for scope in ("tracks", "albums", "artists"):
                items = entry.get(scope, [])
                fetched_at = entry.get(f"{scope}_fetched_at", now)
                scope_rows.append((username, scope, fetched_at))
                for item in items:
                    track_rows.append((
                        username,
                        scope,
                        item.get("mbid") or "",
                        item.get("name", ""),
                        item.get("artist") or "",
                        item.get("playcount") or 0,
                        item.get("rank"),
                        item.get("album"),
                        fetched_at,
                    ))
        conn.executemany(
            "INSERT OR IGNORE INTO lfm_scopes (username, scope, fetched_at) VALUES (?, ?, ?)",
            scope_rows,
        )
        conn.executemany(
            """INSERT OR IGNORE INTO lfm_tracks
               (username, scope, mbid, name, artist, playcount, rank, album, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            track_rows,
        )
        _set_meta(conn, "gzip_lfm_migrated", "1")
        conn.commit()
        logger.info("LFM gzip migration complete: %d track/album/artist records", len(track_rows))
    except Exception as exc:
        logger.error("Failed to migrate LFM gzip cache: %s", exc)
