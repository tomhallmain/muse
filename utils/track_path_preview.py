"""
Shared filepath preview for track metadata / rename UI.

Computes the on-disk path that would result from applying metadata and optional
directory / file actions. Used by TrackDetailsWindow (default actions: tag-only
dirs, rename file when title changes) and RenameConfirmationWindow (user-selected
actions).
"""

from __future__ import annotations

import os
from enum import Enum
from typing import List, Optional

class DirAction(str, Enum):
    NONE       = "none"
    RENAME     = "rename"
    MOVE_EXIST = "move_existing"
    MOVE_NEW   = "move_new"


class TrackActionKey(str, Enum):
    """Keys for the actions dict passed from RenameConfirmationWindow to _on_rename_confirmed."""
    RENAME_FILE  = "rename_track_file"
    RETAIN_IDS   = "retain_ids"
    ALBUM_ACTION = "album_action"
    ALBUM_TARGET = "album_target"
    ARTIST_ACTION = "artist_action"
    ARTIST_TARGET = "artist_target"


def compute_proposed_filepath(
    track,
    metadata: dict,
    *,
    rename_track_file: bool = False,
    retain_ids: bool = False,
    id_tags: Optional[List[str]] = None,
    artist_action: str = DirAction.NONE,
    album_action: str = DirAction.NONE,
    artist_target: str = "",
    album_target: str = "",
) -> str:
    """Return the absolute path after applying *metadata* and *actions*."""
    from library_data.media_track import MediaTrack

    current_file = os.path.normpath(track.filepath)
    current_album_dir = os.path.dirname(current_file)
    current_artist_dir = os.path.dirname(current_album_dir)
    music_root = os.path.dirname(current_artist_dir)

    if artist_action == DirAction.RENAME:
        new_artist = MediaTrack.sanitize_filename_stem(
            metadata.get("artist", "") or track.artist or ""
        )
        new_artist_dir = os.path.join(music_root, new_artist)
    elif artist_action in (DirAction.MOVE_EXIST, DirAction.MOVE_NEW):
        new_artist_dir = artist_target.strip() or current_artist_dir
    else:
        new_artist_dir = current_artist_dir

    if album_action == DirAction.RENAME:
        new_album = MediaTrack.sanitize_filename_stem(
            metadata.get("album", "") or track.album or ""
        )
        new_album_dir = os.path.join(new_artist_dir, new_album)
    elif album_action in (DirAction.MOVE_EXIST, DirAction.MOVE_NEW):
        new_album_dir = album_target.strip() or current_album_dir
    else:
        new_album_dir = os.path.join(
            new_artist_dir, os.path.basename(current_album_dir)
        )

    basename = track.basename
    if rename_track_file:
        title = metadata["title"] if "title" in metadata else (track.title or "")
        stem = MediaTrack.sanitize_filename_stem(title)
        if retain_ids and id_tags:
            stem = MediaTrack.reattach_ids(stem, id_tags)
        if stem:
            basename = stem + track.ext

    return os.path.join(new_album_dir, basename)
