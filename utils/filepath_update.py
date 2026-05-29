"""
Propagate a file or directory rename to every filepath-keyed cache in the app.

After a successful os.rename(), call one of:
    propagate_file_rename(old_path, new_path)
    propagate_directory_rename(old_dir, new_dir)

These functions are best-effort: each cache update is wrapped in its own
try/except so a failure in one cache does not abort the others.  Errors are
logged as warnings rather than raised.

Directory renames are handled recursively: renaming an artist directory (two
levels above a track file) correctly rewrites all album-level and file-level
paths beneath it, not just paths whose immediate parent matches old_dir.

Caches covered
--------------
┌─────────────────────────────────┬──────────────────────────────┬──────────────────┐
│ Store                           │ Key / field                  │ Update strategy  │
├─────────────────────────────────┼──────────────────────────────┼──────────────────┤
│ DB: media_tracks                │ filepath (PK)                │ UPDATE … = ?     │
│ DB: media_tracks                │ parent_filepath              │ UPDATE … = ?     │
│ DB: directories.path            │ path (PK)                    │ INSERT+DELETE    │
│ DB: directories.files           │ JSON array of filepaths      │ parse/rewrite    │
│ LibraryData.MEDIA_TRACK_CACHE   │ {filepath: MediaTrack}       │ re-key dict      │
│ LibraryData.DIRECTORIES_CACHE   │ {dir: [filepath, …]}         │ re-key + rewrite │
│ LibraryData.all_tracks          │ flat list of MediaTrack objs │ update .filepath │
│ Playlist.recently_played_fp     │ list of filepaths            │ replace + store  │
│ app_info_cache: last_session    │ resolved_tracks list + cur   │ load/patch/store │
│ app_info_cache: favorites       │ Favorite.filepath hint       │ load/patch/store │
└─────────────────────────────────┴──────────────────────────────┴──────────────────┘
"""

from __future__ import annotations

import json
import os
from typing import Callable

from utils.logging_setup import get_logger

logger = get_logger(__name__)


def _norm(path: str) -> str:
    return os.path.normpath(path)


def _remap_under(old_dir: str, new_dir: str, path: str) -> str:
    """Return *path* with its *old_dir* prefix replaced by *new_dir*.

    Works for both direct children (album rename) and deeper descendants
    (artist rename where the track is at Artist/Album/track.flac).
    Returns *path* unchanged when it is not under *old_dir*.
    """
    try:
        rel = os.path.relpath(_norm(path), _norm(old_dir))
    except ValueError:
        return path  # different drive on Windows
    if rel.startswith(".."):
        return path  # not under old_dir
    return new_dir if rel == "." else os.path.join(new_dir, rel)


def _guarded(label: str, fn: Callable) -> None:
    """Call *fn* and log any exception as a warning rather than raising."""
    try:
        fn()
    except Exception as exc:
        logger.warning("Cache update skipped (%s): %s", label, exc)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def propagate_file_rename(old_path: str, new_path: str) -> None:
    """Update every filepath-keyed cache after a single file has been renamed."""
    _guarded("db:media_tracks",      lambda: _db_file(old_path, new_path))
    _guarded("db:directories.files", lambda: _db_dir_json_file(old_path, new_path))
    _guarded("LibraryData",          lambda: _lib_file(old_path, new_path))
    _guarded("Playlist.history",     lambda: _playlist_file(old_path, new_path))
    _guarded("PlaybackSession",      lambda: _session_file(old_path, new_path))
    _guarded("Favorites",            lambda: _favorites_file(old_path, new_path))


def propagate_directory_rename(old_dir: str, new_dir: str) -> None:
    """Update every filepath-keyed cache after a directory has been renamed."""
    _guarded("db:media_tracks+dirs", lambda: _db_directory(old_dir, new_dir))
    _guarded("LibraryData",          lambda: _lib_directory(old_dir, new_dir))
    _guarded("Playlist.history",     lambda: _playlist_directory(old_dir, new_dir))
    _guarded("PlaybackSession",      lambda: _session_directory(old_dir, new_dir))
    _guarded("Favorites",            lambda: _favorites_directory(old_dir, new_dir))


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _db_file(old_path: str, new_path: str) -> None:
    from utils.db import get_connection
    conn = get_connection()
    conn.execute(
        "UPDATE media_tracks SET filepath=? WHERE filepath=?",
        (new_path, old_path),
    )
    conn.execute(
        "UPDATE media_tracks SET parent_filepath=? WHERE parent_filepath=?",
        (new_path, old_path),
    )
    conn.commit()


def _db_dir_json_file(old_path: str, new_path: str) -> None:
    """Update the filepath inside the directories.files JSON array."""
    from utils.db import get_connection
    dir_path = os.path.dirname(old_path)
    conn = get_connection()
    row = conn.execute(
        "SELECT files FROM directories WHERE path=?", (dir_path,)
    ).fetchone()
    if not row:
        return
    try:
        files: list = json.loads(row["files"] or "[]")
        updated = [new_path if _norm(f) == _norm(old_path) else f for f in files]
        if updated != files:
            conn.execute(
                "UPDATE directories SET files=? WHERE path=?",
                (json.dumps(updated), dir_path),
            )
            conn.commit()
    except json.JSONDecodeError:
        pass


def _db_directory(old_dir: str, new_dir: str) -> None:
    """Rename a directory in the DB: bulk-update all track paths and re-key
    the directories row."""
    from utils.db import get_connection
    # Use forward-slash normalised prefix for the SQL replace() call so it
    # works reliably on Windows where paths may mix separators.
    old_prefix_fwd = old_dir.replace("\\", "/") + "/"
    new_prefix_fwd = new_dir.replace("\\", "/") + "/"

    conn = get_connection()
    conn.execute(
        "UPDATE media_tracks "
        "SET filepath = replace(replace(filepath,'\\\\','/'), ?, ?) "
        "WHERE replace(replace(filepath,'\\\\','/'), '\\\\', '/') LIKE ?",
        (old_prefix_fwd, new_prefix_fwd, old_prefix_fwd + "%"),
    )
    conn.execute(
        "UPDATE media_tracks "
        "SET parent_filepath = replace(replace(parent_filepath,'\\\\','/'), ?, ?) "
        "WHERE replace(replace(parent_filepath,'\\\\','/'), '\\\\', '/') LIKE ?",
        (old_prefix_fwd, new_prefix_fwd, old_prefix_fwd + "%"),
    )

    # Re-key the directories row and update its files JSON.
    row = conn.execute(
        "SELECT files, scanned_at FROM directories WHERE path=?", (old_dir,)
    ).fetchone()
    if row:
        try:
            files: list = json.loads(row["files"] or "[]")
            updated = [
                os.path.join(new_dir, os.path.basename(f))
                if _norm(os.path.dirname(f)) == _norm(old_dir) else f
                for f in files
            ]
            conn.execute(
                "INSERT OR REPLACE INTO directories (path, files, scanned_at) "
                "VALUES (?, ?, ?)",
                (new_dir, json.dumps(updated), row["scanned_at"]),
            )
            conn.execute("DELETE FROM directories WHERE path=?", (old_dir,))
        except json.JSONDecodeError:
            pass

    conn.commit()


# ---------------------------------------------------------------------------
# In-memory LibraryData caches
# ---------------------------------------------------------------------------

def _lib_file(old_path: str, new_path: str) -> None:
    from library_data.library_data import LibraryData

    # MEDIA_TRACK_CACHE
    track = LibraryData.MEDIA_TRACK_CACHE.pop(old_path, None)
    if track is not None:
        track.filepath = new_path
        LibraryData.MEDIA_TRACK_CACHE[new_path] = track

    # all_tracks flat list (values may overlap with MEDIA_TRACK_CACHE)
    for t in LibraryData.all_tracks:
        if _norm(t.filepath) == _norm(old_path):
            t.filepath = new_path
            break

    # DIRECTORIES_CACHE entry for the file's directory
    dir_path = os.path.dirname(old_path)
    if dir_path in LibraryData.DIRECTORIES_CACHE:
        LibraryData.DIRECTORIES_CACHE[dir_path] = [
            new_path if _norm(f) == _norm(old_path) else f
            for f in LibraryData.DIRECTORIES_CACHE[dir_path]
        ]


def _lib_directory(old_dir: str, new_dir: str) -> None:
    from library_data.library_data import LibraryData

    # Re-key MEDIA_TRACK_CACHE for every file anywhere under old_dir
    # (handles both album renames and artist renames recursively).
    to_move = {k: v for k, v in LibraryData.MEDIA_TRACK_CACHE.items()
               if _remap_under(old_dir, new_dir, k) != k}
    for old_p, track in to_move.items():
        new_p = _remap_under(old_dir, new_dir, old_p)
        del LibraryData.MEDIA_TRACK_CACHE[old_p]
        track.filepath = new_p
        LibraryData.MEDIA_TRACK_CACHE[new_p] = track

    for t in LibraryData.all_tracks:
        remapped = _remap_under(old_dir, new_dir, t.filepath)
        if remapped != t.filepath:
            t.filepath = remapped

    # Re-key every DIRECTORIES_CACHE entry at or under old_dir
    to_rekeye = {k: v for k, v in LibraryData.DIRECTORIES_CACHE.items()
                 if _remap_under(old_dir, new_dir, k) != k}
    for old_k, files in to_rekeye.items():
        del LibraryData.DIRECTORIES_CACHE[old_k]
        new_k = _remap_under(old_dir, new_dir, old_k)
        LibraryData.DIRECTORIES_CACHE[new_k] = [
            _remap_under(old_dir, new_dir, f) for f in files
        ]


# ---------------------------------------------------------------------------
# Playlist history (in-memory + app_info_cache)
# ---------------------------------------------------------------------------

def _playlist_file(old_path: str, new_path: str) -> None:
    from muse.playlist import Playlist
    from utils.globals import HistoryType
    key = HistoryType.TRACKS.value

    # Update the live in-memory list
    Playlist.recently_played_filepaths = [
        new_path if _norm(f) == _norm(old_path) else f
        for f in Playlist.recently_played_filepaths
    ]
    # Persist the change so it survives restart
    from utils.app_info_cache import app_info_cache
    cached = app_info_cache.get(key, [])
    updated = [new_path if _norm(f) == _norm(old_path) else f for f in cached]
    if updated != cached:
        app_info_cache.set(key, updated)
        app_info_cache.store()


def _playlist_directory(old_dir: str, new_dir: str) -> None:
    from muse.playlist import Playlist
    from utils.globals import HistoryType
    key = HistoryType.TRACKS.value

    Playlist.recently_played_filepaths = [
        _remap_under(old_dir, new_dir, f) for f in Playlist.recently_played_filepaths
    ]

    from utils.app_info_cache import app_info_cache
    cached = app_info_cache.get(key, [])
    updated = [_remap_under(old_dir, new_dir, f) for f in cached]
    if updated != cached:
        app_info_cache.set(key, updated)
        app_info_cache.store()


# ---------------------------------------------------------------------------
# PlaybackSession
# ---------------------------------------------------------------------------

def _session_file(old_path: str, new_path: str) -> None:
    from muse.playback_session import LAST_SESSION_KEY
    from utils.app_info_cache import app_info_cache

    session = app_info_cache.get(LAST_SESSION_KEY)
    if not isinstance(session, dict):
        return

    changed = False
    if _norm(session.get("current_track_filepath", "")) == _norm(old_path):
        session["current_track_filepath"] = new_path
        changed = True

    tracks = session.get("resolved_tracks", [])
    new_tracks = [new_path if _norm(t) == _norm(old_path) else t for t in tracks]
    if new_tracks != tracks:
        session["resolved_tracks"] = new_tracks
        changed = True

    if changed:
        app_info_cache.set(LAST_SESSION_KEY, session)
        app_info_cache.store()


def _session_directory(old_dir: str, new_dir: str) -> None:
    from muse.playback_session import LAST_SESSION_KEY
    from utils.app_info_cache import app_info_cache

    session = app_info_cache.get(LAST_SESSION_KEY)
    if not isinstance(session, dict):
        return

    changed = False
    cur = session.get("current_track_filepath", "")
    new_cur = _remap_under(old_dir, new_dir, cur)
    if new_cur != cur:
        session["current_track_filepath"] = new_cur
        changed = True

    tracks = session.get("resolved_tracks", [])
    new_tracks = [_remap_under(old_dir, new_dir, t) for t in tracks]
    if new_tracks != tracks:
        session["resolved_tracks"] = new_tracks
        changed = True

    if changed:
        app_info_cache.set(LAST_SESSION_KEY, session)
        app_info_cache.store()


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------

def _favorites_file(old_path: str, new_path: str) -> None:
    from utils.app_info_cache import app_info_cache
    favs = app_info_cache.get("favorites", [])
    if not isinstance(favs, list):
        return
    changed = False
    for fav in favs:
        if isinstance(fav, dict) and _norm(fav.get("filepath", "")) == _norm(old_path):
            fav["filepath"] = new_path
            changed = True
    if changed:
        app_info_cache.set("favorites", favs)
        app_info_cache.store()


def _favorites_directory(old_dir: str, new_dir: str) -> None:
    from utils.app_info_cache import app_info_cache
    favs = app_info_cache.get("favorites", [])
    if not isinstance(favs, list):
        return
    changed = False
    for fav in favs:
        if isinstance(fav, dict):
            fp = fav.get("filepath", "")
            if fp:
                new_fp = _remap_under(old_dir, new_dir, fp)
                if new_fp != fp:
                    fav["filepath"] = new_fp
                    changed = True
    if changed:
        app_info_cache.set("favorites", favs)
        app_info_cache.store()
