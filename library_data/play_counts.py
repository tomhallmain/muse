"""Per-track play counts, kept apart from the track cache.

A play is recorded when enough of a track was actually heard (counts_as_play).
Rows are keyed by (kind, key): library files use kind FILE and their filepath;
titles heard on a radio stream use kind STREAM and stream_key(artist, title).
Each row also keeps the artist, album, title and track number seen at its
latest play, so a row whose path no longer exists can be matched back by tags.
"""

import datetime
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from utils.config import config
from utils.db import get_connection
from utils.logging_setup import get_logger
from utils.name_ops import NameOps

logger = get_logger(__name__)

FILE = "file"
STREAM = "stream"

_SNAPSHOT_COLUMNS = ("artist", "album", "title", "tracknumber")


@dataclass
class PlayInfo:
    play_count: int
    first_played: Optional[datetime.datetime]
    last_played: Optional[datetime.datetime]


def counts_as_play(listened_seconds: float, length_seconds: Optional[float]) -> bool:
    """Whether hearing listened_seconds of a track of length_seconds is a play.

    An unknown or non-positive length never counts: there is nothing to take
    a fraction of.
    """
    if not length_seconds or length_seconds <= 0 or listened_seconds <= 0:
        return False
    cap = config.play_count_threshold_cap_seconds
    if cap > 0 and listened_seconds >= cap:
        return True
    return listened_seconds >= config.play_count_threshold_ratio * length_seconds


def record_play(track: Any, when: Optional[datetime.datetime] = None) -> None:
    """Add one play for track's file and refresh its tag snapshot."""
    filepath = getattr(track, "filepath", None)
    if not filepath:
        return
    stamp = (when or datetime.datetime.now()).isoformat()
    tracknumber = getattr(track, "tracknumber", None)
    if tracknumber is None or tracknumber <= 0:
        tracknumber = None
    conn = get_connection()
    conn.execute(
        "INSERT INTO track_plays (kind, key, play_count, first_played, last_played, "
        "artist, album, title, tracknumber) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(kind, key) DO UPDATE SET "
        "play_count = play_count + 1, "
        "first_played = COALESCE(first_played, excluded.first_played), "
        "last_played = excluded.last_played, "
        "artist = excluded.artist, album = excluded.album, "
        "title = excluded.title, tracknumber = excluded.tracknumber",
        (FILE, filepath, stamp, stamp, getattr(track, "artist", None),
         getattr(track, "album", None), getattr(track, "title", None), tracknumber),
    )
    conn.commit()


def stream_key(artist: Optional[str], title: Optional[str]) -> Optional[str]:
    """The key a stream title is recorded under, or None if there is no title.

    Folded so that the same track sent with different case, accents or
    punctuation by different stations is one key.
    """
    title_folded = NameOps.fold(title)
    if not title_folded:
        return None
    artist_folded = NameOps.fold(artist)
    return f"{artist_folded} - {title_folded}" if artist_folded else title_folded


def record_stream_title(artist: Optional[str], title: Optional[str], station_name: Optional[str] = None,
                        when: Optional[datetime.datetime] = None) -> None:
    """Add one play for a title heard on a stream; the station goes in the album column."""
    key = stream_key(artist, title)
    if key is None:
        return
    stamp = (when or datetime.datetime.now()).isoformat()
    conn = get_connection()
    conn.execute(
        "INSERT INTO track_plays (kind, key, play_count, first_played, last_played, "
        "artist, album, title, tracknumber) VALUES (?, ?, 1, ?, ?, ?, ?, ?, NULL) "
        "ON CONFLICT(kind, key) DO UPDATE SET "
        "play_count = play_count + 1, "
        "first_played = COALESCE(first_played, excluded.first_played), "
        "last_played = excluded.last_played, "
        "artist = excluded.artist, album = excluded.album, title = excluded.title",
        (STREAM, key, stamp, stamp, artist or None, station_name or None, title),
    )
    conn.commit()


def is_stream_title_heard(artist: Optional[str], title: Optional[str]) -> bool:
    key = stream_key(artist, title)
    if key is None:
        return False
    row = get_connection().execute(
        "SELECT 1 FROM track_plays WHERE kind = ? AND key = ?", (STREAM, key)
    ).fetchone()
    return row is not None


def _parse_time(value: Optional[str]) -> Optional[datetime.datetime]:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        return None


def get_play_info(filepath: str) -> Optional[PlayInfo]:
    """Count and first/last play times for a file, or None if it was never counted."""
    row = get_connection().execute(
        "SELECT play_count, first_played, last_played FROM track_plays WHERE kind = ? AND key = ?",
        (FILE, filepath),
    ).fetchone()
    if row is None:
        return None
    return PlayInfo(row["play_count"], _parse_time(row["first_played"]), _parse_time(row["last_played"]))


def get_all_play_info() -> Dict[str, PlayInfo]:
    """Every counted file's count and first/last play times, by filepath."""
    rows = get_connection().execute(
        "SELECT key, play_count, first_played, last_played FROM track_plays WHERE kind = ?", (FILE,)
    ).fetchall()
    return {
        row["key"]: PlayInfo(row["play_count"], _parse_time(row["first_played"]), _parse_time(row["last_played"]))
        for row in rows
    }


def get_play_counts() -> Dict[str, int]:
    """Every counted file's play count, by filepath."""
    rows = get_connection().execute(
        "SELECT key, play_count FROM track_plays WHERE kind = ?", (FILE,)
    ).fetchall()
    return {row["key"]: row["play_count"] for row in rows}


# ── Path changes (called from utils/filepath_update.py) ────────────────────────

def file_keys() -> List[str]:
    rows = get_connection().execute("SELECT key FROM track_plays WHERE kind = ?", (FILE,)).fetchall()
    return [row["key"] for row in rows]


def rekey_files(mapping: Dict[str, str]) -> None:
    """Move each old filepath's row to its new filepath.

    If the new path already has a row (left by a file removed outside the app),
    the two are merged: counts summed, the earlier first play, the later last
    play, and the tag snapshot from whichever was played last.
    """
    conn = get_connection()
    for old, new in mapping.items():
        if old == new:
            continue
        source = _row(conn, old)
        if source is None:
            continue
        target = _row(conn, new)
        if target is None:
            conn.execute("UPDATE track_plays SET key = ? WHERE kind = ? AND key = ?", (new, FILE, old))
            continue
        latest = source if (source["last_played"] or "") > (target["last_played"] or "") else target
        firsts = [t for t in (source["first_played"], target["first_played"]) if t]
        conn.execute(
            "UPDATE track_plays SET play_count = ?, first_played = ?, last_played = ?, "
            "artist = ?, album = ?, title = ?, tracknumber = ? WHERE kind = ? AND key = ?",
            (source["play_count"] + target["play_count"], min(firsts) if firsts else None,
             latest["last_played"], *(latest[c] for c in _SNAPSHOT_COLUMNS), FILE, new),
        )
        conn.execute("DELETE FROM track_plays WHERE kind = ? AND key = ?", (FILE, old))
    conn.commit()


def delete_files(filepaths: Iterable[str]) -> None:
    conn = get_connection()
    conn.executemany(
        "DELETE FROM track_plays WHERE kind = ? AND key = ?", [(FILE, f) for f in filepaths]
    )
    conn.commit()


def _row(conn, filepath: str):
    return conn.execute(
        "SELECT * FROM track_plays WHERE kind = ? AND key = ?", (FILE, filepath)
    ).fetchone()
