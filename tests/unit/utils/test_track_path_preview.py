"""
Tests for utils/track_path_preview.py (gap #6 — preview alignment).

All tests use a lightweight stub track (SimpleNamespace) and call
compute_proposed_filepath directly.  No DB, Qt, or app_info_cache dependency.
"""

import os
from types import SimpleNamespace

import pytest

from utils.track_path_preview import (
    DIR_ACTION_MOVE_EXIST,
    DIR_ACTION_MOVE_NEW,
    DIR_ACTION_NONE,
    DIR_ACTION_RENAME,
    compute_proposed_filepath,
)

# ---------------------------------------------------------------------------
# Fixture: minimal stub track
# ---------------------------------------------------------------------------

MUSIC_ROOT = "/music"
TRACK_PATH = "/music/Artist/Album/track.flac"


def make_track(
    filepath=TRACK_PATH,
    basename="track.flac",
    ext=".flac",
    title="Track Title",
    artist="Artist",
    album="Album",
):
    return SimpleNamespace(
        filepath=filepath,
        basename=basename,
        ext=ext,
        title=title,
        artist=artist,
        album=album,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestComputeProposedFilepath:
    def test_no_changes_returns_current_path(self):
        result = compute_proposed_filepath(make_track(), {})
        assert result == os.path.normpath(TRACK_PATH)

    def test_title_changed_renames_file_basename(self):
        result = compute_proposed_filepath(
            make_track(), {"title": "New Title"}, rename_track_file=True
        )
        assert os.path.basename(result) == "New Title.flac"
        assert os.path.dirname(result) == os.path.normpath("/music/Artist/Album")

    def test_rename_file_false_leaves_basename_unchanged(self):
        result = compute_proposed_filepath(
            make_track(), {"title": "New Title"}, rename_track_file=False
        )
        assert os.path.basename(result) == "track.flac"

    def test_empty_sanitized_title_leaves_basename_unchanged(self):
        # A title that sanitizes to empty (e.g. only illegal chars) keeps the original basename.
        result = compute_proposed_filepath(
            make_track(), {"title": ""},
            rename_track_file=True,
        )
        assert os.path.basename(result) == "track.flac"

    def test_retain_ids_reattaches_bracket_tags(self):
        result = compute_proposed_filepath(
            make_track(), {"title": "New Title"},
            rename_track_file=True,
            retain_ids=True,
            id_tags=["FLAC"],
        )
        assert os.path.basename(result) == "New Title [FLAC].flac"

    def test_retain_ids_false_does_not_append_tags(self):
        result = compute_proposed_filepath(
            make_track(), {"title": "New Title"},
            rename_track_file=True,
            retain_ids=False,
            id_tags=["FLAC"],
        )
        assert "[FLAC]" not in os.path.basename(result)

    def test_artist_rename_action_changes_artist_directory(self):
        result = compute_proposed_filepath(
            make_track(), {"artist": "NewArtist"},
            artist_action=DIR_ACTION_RENAME,
        )
        parts = result.split(os.sep)
        assert "NewArtist" in parts
        assert "Artist" not in parts

    def test_album_rename_action_changes_album_directory(self):
        result = compute_proposed_filepath(
            make_track(), {"album": "NewAlbum"},
            album_action=DIR_ACTION_RENAME,
        )
        parts = result.split(os.sep)
        assert "NewAlbum" in parts
        assert "Album" not in parts

    def test_artist_and_album_rename_compose_correctly(self):
        result = compute_proposed_filepath(
            make_track(),
            {"artist": "NewArtist", "album": "NewAlbum"},
            artist_action=DIR_ACTION_RENAME,
            album_action=DIR_ACTION_RENAME,
        )
        assert result.startswith(os.path.normpath("/music/NewArtist/NewAlbum") + os.sep)

    def test_artist_move_existing_uses_provided_target(self):
        result = compute_proposed_filepath(
            make_track(), {},
            artist_action=DIR_ACTION_MOVE_EXIST,
            artist_target="/other/location",
        )
        # Album stays under the new artist target; file stays the same.
        assert result.startswith("/other/location")

    def test_album_move_existing_uses_provided_target(self):
        result = compute_proposed_filepath(
            make_track(), {},
            album_action=DIR_ACTION_MOVE_EXIST,
            album_target="/other/album",
        )
        assert result.startswith("/other/album")

    def test_artist_dir_action_none_keeps_artist_directory(self):
        result = compute_proposed_filepath(
            make_track(), {"artist": "NewArtist"},
            artist_action=DIR_ACTION_NONE,
        )
        # With NONE, artist dir is unchanged even if the metadata field differs.
        assert os.path.normpath("/music/Artist") in result
