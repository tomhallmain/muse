"""
Propagate a file or directory rename to every filepath-keyed cache in the app.

After a successful on-disk rename/move (``utils.path_move.move_on_disk``), call:
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
│ DB: directories.path            │ path (PK)                    │ re-key all under │
│ DB: directories.files           │ JSON array of filepaths      │ _remap_under     │
│ LibraryData.MEDIA_TRACK_CACHE   │ {filepath: MediaTrack}       │ re-key dict      │
│ LibraryData.DIRECTORIES_CACHE   │ {dir: [filepath, …]}         │ re-key + rewrite │
│ LibraryData.all_tracks          │ flat list of MediaTrack objs │ update .filepath │
│ Playlist.recently_played_fp     │ list of filepaths            │ replace + store  │
│ app_info_cache: last_session    │ resolved_tracks + descriptor │ load/patch/store │
│ app_info_cache: favorites       │ Favorite.filepath hint       │ load/patch/store │
│ app_info_cache: playlist_desc   │ track_filepaths, source_dirs │ load/patch/store │
│ app_info_cache: recent_desc     │ same fields per recent entry │ load/patch/store │
└─────────────────────────────────┴──────────────────────────────┴──────────────────┘

propagate_file_delete covers the same set of stores, removing every reference to the
deleted path rather than remapping it.
"""

from __future__ import annotations

import json
import os
from typing import Callable

from utils.logging_setup import get_logger

logger = get_logger(__name__)


def _norm(path: str) -> str:
    return os.path.normpath(path)


def _is_cross_directory_move(old_path: str, new_path: str) -> bool:
    """True when *new_path* is in a different parent directory than *old_path*."""
    return _norm(os.path.dirname(old_path)) != _norm(os.path.dirname(new_path))


def _remap_under(old_dir: str, new_dir: str, path: str) -> str:
    """Return *path* with its *old_dir* prefix replaced by *new_dir*.

    Works for both direct children (album rename) and deeper descendants
    (artist rename where the track is at Artist/Album/track.flac).
    Returns *path* unchanged when it is not under *old_dir*.
    """
    from utils.path_move import normcase_path

    old_n = _norm(old_dir)
    new_n = _norm(new_dir)
    path_n = _norm(path)
    try:
        rel = os.path.relpath(path_n, old_n)
    except ValueError:
        # Different drives (Windows): prefix replace when path is under old_dir.
        old_c = normcase_path(old_n)
        path_c = normcase_path(path_n)
        if path_c == old_c:
            return new_n
        prefix = old_c + os.sep
        if not path_c.startswith(prefix):
            return path
        rest = path_n[len(old_n) :].lstrip(os.sep)
        return new_n if not rest else os.path.join(new_n, rest)
    if rel.startswith(".."):
        return path  # not under old_dir
    return new_n if rel == "." else os.path.join(new_n, rel)


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
    _guarded("PlaylistDescriptors",  lambda: _playlist_descriptors_file(old_path, new_path))


def propagate_directory_rename(old_dir: str, new_dir: str) -> None:
    """Update every filepath-keyed cache after a directory has been renamed."""
    _guarded("db:media_tracks+dirs", lambda: _db_directory(old_dir, new_dir))
    _guarded("LibraryData",          lambda: _lib_directory(old_dir, new_dir))
    _guarded("Playlist.history",     lambda: _playlist_directory(old_dir, new_dir))
    _guarded("PlaybackSession",      lambda: _session_directory(old_dir, new_dir))
    _guarded("Favorites",            lambda: _favorites_directory(old_dir, new_dir))
    _guarded("PlaylistDescriptors",  lambda: _playlist_descriptors_directory(old_dir, new_dir))


def propagate_file_delete(filepath: str) -> None:
    """Remove every reference to filepath from all caches after the file is deleted."""
    _guarded("db:media_tracks",      lambda: _db_file_delete(filepath))
    _guarded("db:directories.files", lambda: _db_dir_json_file_delete(filepath))
    _guarded("LibraryData",          lambda: _lib_file_delete(filepath))
    _guarded("Playlist.history",     lambda: _playlist_file_delete(filepath))
    _guarded("PlaybackSession",      lambda: _session_file_delete(filepath))
    _guarded("Favorites",            lambda: _favorites_file_delete(filepath))
    _guarded("PlaylistDescriptors",  lambda: _playlist_descriptors_file_delete(filepath))


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


def _db_dir_append_file(conn, dir_path: str, file_path: str) -> bool:
    """Append *file_path* to ``directories.files`` for *dir_path*.

    Used only for cross-directory moves. Returns True if the DB was mutated.
    """
    import time

    row = conn.execute(
        "SELECT files, scanned_at FROM directories WHERE path=?", (dir_path,)
    ).fetchone()
    if row:
        try:
            files: list = json.loads(row["files"] or "[]")
        except json.JSONDecodeError:
            files = []
        if any(_norm(f) == _norm(file_path) for f in files):
            return False
        files.append(file_path)
        conn.execute(
            "UPDATE directories SET files=? WHERE path=?",
            (json.dumps(files), dir_path),
        )
        return True

    conn.execute(
        "INSERT OR REPLACE INTO directories (path, files, scanned_at) "
        "VALUES (?, ?, ?)",
        (dir_path, json.dumps([file_path]), time.time()),
    )
    return True


def _db_dir_json_file(old_path: str, new_path: str) -> None:
    """Update ``directories.files`` for a single-file rename or cross-dir move."""
    from utils.db import get_connection

    old_dir = os.path.dirname(old_path)
    cross = _is_cross_directory_move(old_path, new_path)
    conn = get_connection()
    changed = False

    row = conn.execute(
        "SELECT files FROM directories WHERE path=?", (old_dir,)
    ).fetchone()
    if row:
        try:
            files: list = json.loads(row["files"] or "[]")
            if cross:
                updated = [f for f in files if _norm(f) != _norm(old_path)]
            else:
                updated = [
                    new_path if _norm(f) == _norm(old_path) else f for f in files
                ]
            if updated != files:
                conn.execute(
                    "UPDATE directories SET files=? WHERE path=?",
                    (json.dumps(updated), old_dir),
                )
                changed = True
        except json.JSONDecodeError:
            pass

    if cross and _db_dir_append_file(conn, os.path.dirname(new_path), new_path):
        changed = True

    if changed:
        conn.commit()


def _db_directory(old_dir: str, new_dir: str) -> None:
    """Rename a directory in the DB: bulk-update all track paths and re-key
    every ``directories`` row at or under *old_dir* (mirrors ``_lib_directory``).
    """
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

    # Re-key every directories row whose path is old_dir or a descendant.
    rows = conn.execute(
        "SELECT path, files, scanned_at FROM directories"
    ).fetchall()
    to_rekey = [
        row for row in rows
        if _remap_under(old_dir, new_dir, row["path"]) != row["path"]
    ]
    for row in to_rekey:
        old_path = row["path"]
        new_path = _remap_under(old_dir, new_dir, old_path)
        try:
            files: list = json.loads(row["files"] or "[]")
            updated_files = [_remap_under(old_dir, new_dir, f) for f in files]
        except json.JSONDecodeError:
            updated_files = []
        conn.execute(
            "INSERT OR REPLACE INTO directories (path, files, scanned_at) "
            "VALUES (?, ?, ?)",
            (new_path, json.dumps(updated_files), row["scanned_at"]),
        )
        conn.execute("DELETE FROM directories WHERE path=?", (old_path,))

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

    # DIRECTORIES_CACHE: same-dir rename updates path in place; cross-dir move
    # removes from source and appends to destination.
    old_dir = os.path.dirname(old_path)
    cross = _is_cross_directory_move(old_path, new_path)
    if old_dir in LibraryData.DIRECTORIES_CACHE:
        files = LibraryData.DIRECTORIES_CACHE[old_dir]
        if cross:
            LibraryData.DIRECTORIES_CACHE[old_dir] = [
                f for f in files if _norm(f) != _norm(old_path)
            ]
        else:
            LibraryData.DIRECTORIES_CACHE[old_dir] = [
                new_path if _norm(f) == _norm(old_path) else f for f in files
            ]

    if cross:
        new_dir = os.path.dirname(new_path)
        dest_files = LibraryData.DIRECTORIES_CACHE.get(new_dir)
        if dest_files is None:
            LibraryData.DIRECTORIES_CACHE[new_dir] = [new_path]
        elif not any(_norm(f) == _norm(new_path) for f in dest_files):
            LibraryData.DIRECTORIES_CACHE[new_dir] = list(dest_files) + [new_path]


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

    desc = session.get("descriptor")
    if isinstance(desc, dict) and _patch_descriptor_dict_file(desc, old_path, new_path):
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

    desc = session.get("descriptor")
    if isinstance(desc, dict) and _patch_descriptor_dict_dir(desc, old_dir, new_dir):
        changed = True

    if changed:
        app_info_cache.set(LAST_SESSION_KEY, session)
        app_info_cache.store()


# ---------------------------------------------------------------------------
# Playlist descriptors (app_info_cache)
# ---------------------------------------------------------------------------

def _patch_descriptor_dict_file(data: dict, old_path: str, new_path: str) -> bool:
    """Update a serialised :class:`PlaylistDescriptor` after a file rename."""
    changed = False
    fps = data.get("track_filepaths")
    if isinstance(fps, list):
        new_fps = [new_path if _norm(f) == _norm(old_path) else f for f in fps]
        if new_fps != fps:
            data["track_filepaths"] = new_fps
            changed = True
    return changed


def _patch_descriptor_dict_dir(data: dict, old_dir: str, new_dir: str) -> bool:
    """Update a serialised :class:`PlaylistDescriptor` after a directory rename."""
    changed = False
    fps = data.get("track_filepaths")
    if isinstance(fps, list):
        new_fps = [_remap_under(old_dir, new_dir, f) for f in fps]
        if new_fps != fps:
            data["track_filepaths"] = new_fps
            changed = True
    dirs = data.get("source_directories")
    if isinstance(dirs, list):
        new_dirs = [_remap_under(old_dir, new_dir, d) for d in dirs]
        if new_dirs != dirs:
            data["source_directories"] = new_dirs
            changed = True
    return changed


def _patch_descriptor_list_file(descriptors: list, old_path: str, new_path: str) -> bool:
    changed = False
    for desc in descriptors:
        if isinstance(desc, dict) and _patch_descriptor_dict_file(desc, old_path, new_path):
            changed = True
    return changed


def _patch_descriptor_list_dir(descriptors: list, old_dir: str, new_dir: str) -> bool:
    changed = False
    for desc in descriptors:
        if isinstance(desc, dict) and _patch_descriptor_dict_dir(desc, old_dir, new_dir):
            changed = True
    return changed


def _playlist_descriptors_file(old_path: str, new_path: str) -> None:
    from muse.playlist_descriptor import PLAYLIST_DESCRIPTORS_CACHE_KEY
    from muse.playback_session import RECENT_DESCRIPTORS_KEY
    from utils.app_info_cache import app_info_cache

    raw = app_info_cache.get(PLAYLIST_DESCRIPTORS_CACHE_KEY, {})
    if isinstance(raw, dict):
        changed = _patch_descriptor_list_file(list(raw.values()), old_path, new_path)
        if changed:
            app_info_cache.set(PLAYLIST_DESCRIPTORS_CACHE_KEY, raw)
            app_info_cache.store()

    recents = app_info_cache.get(RECENT_DESCRIPTORS_KEY, []) or []
    if isinstance(recents, list) and _patch_descriptor_list_file(recents, old_path, new_path):
        app_info_cache.set(RECENT_DESCRIPTORS_KEY, recents)
        app_info_cache.store()


def _playlist_descriptors_directory(old_dir: str, new_dir: str) -> None:
    from muse.playlist_descriptor import PLAYLIST_DESCRIPTORS_CACHE_KEY
    from muse.playback_session import RECENT_DESCRIPTORS_KEY
    from utils.app_info_cache import app_info_cache

    raw = app_info_cache.get(PLAYLIST_DESCRIPTORS_CACHE_KEY, {})
    if isinstance(raw, dict):
        changed = _patch_descriptor_list_dir(list(raw.values()), old_dir, new_dir)
        if changed:
            app_info_cache.set(PLAYLIST_DESCRIPTORS_CACHE_KEY, raw)
            app_info_cache.store()

    recents = app_info_cache.get(RECENT_DESCRIPTORS_KEY, []) or []
    if isinstance(recents, list) and _patch_descriptor_list_dir(recents, old_dir, new_dir):
        app_info_cache.set(RECENT_DESCRIPTORS_KEY, recents)
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


# ---------------------------------------------------------------------------
# Delete helpers — remove all references to a deleted filepath
# ---------------------------------------------------------------------------

def _db_file_delete(filepath: str) -> None:
    from utils.db import get_connection
    conn = get_connection()
    conn.execute("DELETE FROM media_tracks WHERE filepath=?", (filepath,))
    conn.commit()


def _db_dir_json_file_delete(filepath: str) -> None:
    from utils.db import get_connection
    old_dir = os.path.dirname(filepath)
    conn = get_connection()
    row = conn.execute(
        "SELECT files FROM directories WHERE path=?", (old_dir,)
    ).fetchone()
    if row:
        try:
            files: list = json.loads(row["files"] or "[]")
            updated = [f for f in files if _norm(f) != _norm(filepath)]
            if updated != files:
                conn.execute(
                    "UPDATE directories SET files=? WHERE path=?",
                    (json.dumps(updated), old_dir),
                )
                conn.commit()
        except json.JSONDecodeError:
            pass


def _lib_file_delete(filepath: str) -> None:
    from library_data.library_data import LibraryData

    LibraryData.MEDIA_TRACK_CACHE.pop(filepath, None)

    LibraryData.all_tracks = [
        t for t in LibraryData.all_tracks if _norm(t.filepath) != _norm(filepath)
    ]

    old_dir = os.path.dirname(filepath)
    if old_dir in LibraryData.DIRECTORIES_CACHE:
        LibraryData.DIRECTORIES_CACHE[old_dir] = [
            f for f in LibraryData.DIRECTORIES_CACHE[old_dir]
            if _norm(f) != _norm(filepath)
        ]


def _playlist_file_delete(filepath: str) -> None:
    from muse.playlist import Playlist
    from utils.globals import HistoryType
    from utils.app_info_cache import app_info_cache
    key = HistoryType.TRACKS.value

    Playlist.recently_played_filepaths = [
        f for f in Playlist.recently_played_filepaths if _norm(f) != _norm(filepath)
    ]
    cached = app_info_cache.get(key, [])
    updated = [f for f in cached if _norm(f) != _norm(filepath)]
    if updated != cached:
        app_info_cache.set(key, updated)
        app_info_cache.store()


def _session_file_delete(filepath: str) -> None:
    from muse.playback_session import LAST_SESSION_KEY
    from utils.app_info_cache import app_info_cache

    session = app_info_cache.get(LAST_SESSION_KEY)
    if not isinstance(session, dict):
        return

    changed = False
    if _norm(session.get("current_track_filepath", "")) == _norm(filepath):
        session["current_track_filepath"] = ""
        changed = True

    tracks = session.get("resolved_tracks", [])
    updated = [t for t in tracks if _norm(t) != _norm(filepath)]
    if updated != tracks:
        session["resolved_tracks"] = updated
        changed = True

    desc = session.get("descriptor")
    if isinstance(desc, dict):
        fps = desc.get("track_filepaths")
        if isinstance(fps, list):
            new_fps = [f for f in fps if _norm(f) != _norm(filepath)]
            if new_fps != fps:
                desc["track_filepaths"] = new_fps
                changed = True

    if changed:
        app_info_cache.set(LAST_SESSION_KEY, session)
        app_info_cache.store()


def _favorites_file_delete(filepath: str) -> None:
    from utils.app_info_cache import app_info_cache
    favs = app_info_cache.get("favorites", [])
    if not isinstance(favs, list):
        return
    updated = [
        f for f in favs
        if not (isinstance(f, dict) and _norm(f.get("filepath", "")) == _norm(filepath))
    ]
    if len(updated) != len(favs):
        app_info_cache.set("favorites", updated)
        app_info_cache.store()


def _playlist_descriptors_file_delete(filepath: str) -> None:
    from muse.playlist_descriptor import PLAYLIST_DESCRIPTORS_CACHE_KEY
    from muse.playback_session import RECENT_DESCRIPTORS_KEY
    from utils.app_info_cache import app_info_cache

    def _remove_from_desc(data: dict) -> bool:
        fps = data.get("track_filepaths")
        if not isinstance(fps, list):
            return False
        updated = [f for f in fps if _norm(f) != _norm(filepath)]
        if updated != fps:
            data["track_filepaths"] = updated
            return True
        return False

    raw = app_info_cache.get(PLAYLIST_DESCRIPTORS_CACHE_KEY, {})
    if isinstance(raw, dict):
        changed = any(_remove_from_desc(v) for v in raw.values() if isinstance(v, dict))
        if changed:
            app_info_cache.set(PLAYLIST_DESCRIPTORS_CACHE_KEY, raw)
            app_info_cache.store()

    recents = app_info_cache.get(RECENT_DESCRIPTORS_KEY, []) or []
    if isinstance(recents, list):
        changed = any(_remove_from_desc(d) for d in recents if isinstance(d, dict))
        if changed:
            app_info_cache.set(RECENT_DESCRIPTORS_KEY, recents)
            app_info_cache.store()
