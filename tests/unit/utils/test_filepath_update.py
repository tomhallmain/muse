"""
Tests for utils/filepath_update.py.

Covers the fixes for gaps #1, #2, and #3 from
docs/track-metadata-path-rename-gaps.md, plus _remap_under cross-drive
behaviour (gap #8).

DB tests use the ``isolated_db`` fixture (see conftest.py).
app_info_cache tests rely on the ``isolated_singletons`` autouse fixture
from the root conftest.
LibraryData cache tests set class-level caches directly; reset_app_globals
(autouse) clears them after each test.
"""

import json
import os

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

P_ARTIST = "/music/Artist"
P_ARTIST2 = "/music/Artist2"
P_ALBUM = "/music/Artist/Album"
P_ALBUM2 = "/music/Artist/Album2"
P_TRACK = "/music/Artist/Album/track.flac"
P_TRACK_NEW = "/music/Artist/Album/new_track.flac"
P_TRACK_XDIR = "/music/Artist/Album2/track.flac"


def _dir_files(conn, path):
    row = conn.execute("SELECT files FROM directories WHERE path=?", (path,)).fetchone()
    if row is None:
        return None
    return json.loads(row["files"])


def _all_paths(conn):
    return {r["path"] for r in conn.execute("SELECT path FROM directories")}


# ---------------------------------------------------------------------------
# Gap #1 + #8: _remap_under (pure function — no DB or cache fixtures needed)
# ---------------------------------------------------------------------------

class TestRemapUnder:
    def test_path_under_old_dir_is_rebased(self):
        from utils.filepath_update import _remap_under

        result = _remap_under(P_ARTIST, P_ARTIST2, "/music/Artist/Album/track.flac")
        assert result == os.path.normpath("/music/Artist2/Album/track.flac")

    def test_exact_old_dir_returns_new_dir(self):
        from utils.filepath_update import _remap_under

        result = _remap_under(P_ARTIST, P_ARTIST2, P_ARTIST)
        assert result == os.path.normpath(P_ARTIST2)

    def test_sibling_path_is_unchanged(self):
        from utils.filepath_update import _remap_under

        sibling = "/music/OtherArtist/track.flac"
        assert _remap_under(P_ARTIST, P_ARTIST2, sibling) == sibling

    def test_cross_drive_fallback_rebases_path(self, monkeypatch):
        """When os.path.relpath raises ValueError (cross-drive), the normcase
        prefix fallback should still remap the path correctly."""
        import utils.filepath_update as fu

        def relpath_raises(p, s):
            raise ValueError("different drives")

        monkeypatch.setattr(fu.os.path, "relpath", relpath_raises)

        result = fu._remap_under(P_ARTIST, P_ARTIST2, "/music/Artist/Album/track.flac")
        assert result == os.path.normpath("/music/Artist2/Album/track.flac")

    def test_cross_drive_fallback_leaves_unrelated_path_unchanged(self, monkeypatch):
        import utils.filepath_update as fu

        def relpath_raises(p, s):
            raise ValueError("different drives")

        monkeypatch.setattr(fu.os.path, "relpath", relpath_raises)

        path = "/other/location/track.flac"
        assert fu._remap_under(P_ARTIST, P_ARTIST2, path) == path


# ---------------------------------------------------------------------------
# Gap #1: _db_directory re-keys nested directories rows
# ---------------------------------------------------------------------------

class TestDbDirectory:
    def test_renames_artist_row(self, isolated_db):
        conn = isolated_db
        conn.execute("INSERT INTO directories VALUES (?, ?, ?)", (P_ARTIST, "[]", 1.0))
        conn.commit()

        from utils.filepath_update import _db_directory
        _db_directory(P_ARTIST, P_ARTIST2)

        paths = _all_paths(conn)
        assert os.path.normpath(P_ARTIST2) in paths
        assert P_ARTIST not in paths

    def test_renames_nested_album_row(self, isolated_db):
        conn = isolated_db
        conn.execute("INSERT INTO directories VALUES (?, ?, ?)", (P_ARTIST, "[]", 1.0))
        conn.execute("INSERT INTO directories VALUES (?, ?, ?)", (P_ALBUM, "[]", 1.0))
        conn.commit()

        from utils.filepath_update import _db_directory
        _db_directory(P_ARTIST, P_ARTIST2)

        paths = _all_paths(conn)
        assert os.path.normpath("/music/Artist2/Album") in paths
        assert P_ALBUM not in paths

    def test_remaps_files_json_in_nested_row(self, isolated_db):
        conn = isolated_db
        conn.execute(
            "INSERT INTO directories VALUES (?, ?, ?)",
            (P_ALBUM, json.dumps([P_TRACK]), 1.0),
        )
        conn.commit()

        from utils.filepath_update import _db_directory
        _db_directory(P_ARTIST, P_ARTIST2)

        new_album = os.path.normpath("/music/Artist2/Album")
        files = _dir_files(conn, new_album)
        assert files is not None
        assert any("Artist2" in f for f in files)
        assert all("Artist/" not in f.split(os.sep) for f in files)

    def test_leaves_unrelated_rows_unchanged(self, isolated_db):
        conn = isolated_db
        other = "/music/OtherArtist"
        conn.execute("INSERT INTO directories VALUES (?, ?, ?)", (P_ARTIST, "[]", 1.0))
        conn.execute("INSERT INTO directories VALUES (?, ?, ?)", (other, "[]", 1.0))
        conn.commit()

        from utils.filepath_update import _db_directory
        _db_directory(P_ARTIST, P_ARTIST2)

        assert other in _all_paths(conn)

    def test_handles_empty_files_json(self, isolated_db):
        conn = isolated_db
        conn.execute("INSERT INTO directories VALUES (?, ?, ?)", (P_ARTIST, "[]", 1.0))
        conn.commit()

        from utils.filepath_update import _db_directory
        _db_directory(P_ARTIST, P_ARTIST2)

        new_artist = os.path.normpath(P_ARTIST2)
        files = _dir_files(conn, new_artist)
        assert files == []


# ---------------------------------------------------------------------------
# Gap #2: _patch_descriptor_dict_* (pure function — no fixtures needed)
# ---------------------------------------------------------------------------

class TestPatchDescriptorDict:
    def test_file_updates_matching_filepath(self):
        from utils.filepath_update import _patch_descriptor_dict_file

        data = {"track_filepaths": [P_TRACK, "/other/track.flac"]}
        changed = _patch_descriptor_dict_file(data, P_TRACK, P_TRACK_NEW)
        assert changed
        assert data["track_filepaths"] == [P_TRACK_NEW, "/other/track.flac"]

    def test_file_no_match_leaves_data_unchanged(self):
        from utils.filepath_update import _patch_descriptor_dict_file

        data = {"track_filepaths": ["/other/track.flac"]}
        changed = _patch_descriptor_dict_file(data, P_TRACK, P_TRACK_NEW)
        assert not changed
        assert data["track_filepaths"] == ["/other/track.flac"]

    def test_file_missing_track_filepaths_key_returns_false(self):
        from utils.filepath_update import _patch_descriptor_dict_file

        data = {}
        assert not _patch_descriptor_dict_file(data, P_TRACK, P_TRACK_NEW)

    def test_dir_remaps_track_filepaths(self):
        from utils.filepath_update import _patch_descriptor_dict_dir

        data = {"track_filepaths": [P_TRACK]}
        changed = _patch_descriptor_dict_dir(data, P_ARTIST, P_ARTIST2)
        assert changed
        assert any("Artist2" in f for f in data["track_filepaths"])

    def test_dir_remaps_source_directories(self):
        from utils.filepath_update import _patch_descriptor_dict_dir

        data = {"source_directories": [P_ARTIST]}
        changed = _patch_descriptor_dict_dir(data, P_ARTIST, P_ARTIST2)
        assert changed
        assert any("Artist2" in d for d in data["source_directories"])

    def test_dir_no_match_returns_false(self):
        from utils.filepath_update import _patch_descriptor_dict_dir

        data = {"track_filepaths": ["/other/Artist/track.flac"]}
        assert not _patch_descriptor_dict_dir(data, P_ARTIST, P_ARTIST2)


# ---------------------------------------------------------------------------
# Gap #2: playlist descriptor cache patching (uses isolated_singletons autouse)
# ---------------------------------------------------------------------------

class TestPlaylistDescriptorsCache:
    def test_file_rename_updates_playlist_descriptor(self):
        from utils.app_info_cache import app_info_cache
        from utils.filepath_update import _playlist_descriptors_file

        desc = {"track_filepaths": [P_TRACK]}
        app_info_cache.set("playlist_descriptors", {"list_a": desc})

        _playlist_descriptors_file(P_TRACK, P_TRACK_NEW)

        raw = app_info_cache.get("playlist_descriptors", {})
        assert raw["list_a"]["track_filepaths"] == [P_TRACK_NEW]

    def test_file_rename_updates_recent_descriptor(self):
        from utils.app_info_cache import app_info_cache
        from utils.filepath_update import _playlist_descriptors_file

        recent = [{"track_filepaths": [P_TRACK]}]
        app_info_cache.set("recent_playlist_descriptors", recent)

        _playlist_descriptors_file(P_TRACK, P_TRACK_NEW)

        stored = app_info_cache.get("recent_playlist_descriptors", [])
        assert stored[0]["track_filepaths"] == [P_TRACK_NEW]

    def test_directory_rename_updates_track_filepaths(self):
        from utils.app_info_cache import app_info_cache
        from utils.filepath_update import _playlist_descriptors_directory

        desc = {"track_filepaths": [P_TRACK]}
        app_info_cache.set("playlist_descriptors", {"list_a": desc})

        _playlist_descriptors_directory(P_ARTIST, P_ARTIST2)

        raw = app_info_cache.get("playlist_descriptors", {})
        assert any("Artist2" in f for f in raw["list_a"]["track_filepaths"])

    def test_directory_rename_updates_source_directories(self):
        from utils.app_info_cache import app_info_cache
        from utils.filepath_update import _playlist_descriptors_directory

        desc = {"source_directories": [P_ARTIST]}
        app_info_cache.set("playlist_descriptors", {"list_a": desc})

        _playlist_descriptors_directory(P_ARTIST, P_ARTIST2)

        raw = app_info_cache.get("playlist_descriptors", {})
        assert any("Artist2" in d for d in raw["list_a"]["source_directories"])

    def test_no_match_does_not_mutate_descriptor(self):
        from utils.app_info_cache import app_info_cache
        from utils.filepath_update import _playlist_descriptors_file

        desc = {"track_filepaths": ["/some/other/track.flac"]}
        app_info_cache.set("playlist_descriptors", {"list_a": desc})

        _playlist_descriptors_file(P_TRACK, P_TRACK_NEW)

        raw = app_info_cache.get("playlist_descriptors", {})
        assert raw["list_a"]["track_filepaths"] == ["/some/other/track.flac"]


# ---------------------------------------------------------------------------
# Gap #2: session descriptor patching (uses isolated_singletons autouse)
# ---------------------------------------------------------------------------

class TestSessionDescriptor:
    def _make_session(self, desc):
        return {
            "current_track_filepath": "/unrelated/track.flac",
            "resolved_tracks": [],
            "descriptor": desc,
        }

    def test_file_rename_patches_session_descriptor(self):
        from utils.app_info_cache import app_info_cache
        from utils.filepath_update import _session_file

        session = self._make_session({"track_filepaths": [P_TRACK]})
        app_info_cache.set("last_playback_session", session)

        _session_file(P_TRACK, P_TRACK_NEW)

        stored = app_info_cache.get("last_playback_session")
        assert stored["descriptor"]["track_filepaths"] == [P_TRACK_NEW]

    def test_directory_rename_patches_session_descriptor(self):
        from utils.app_info_cache import app_info_cache
        from utils.filepath_update import _session_directory

        session = self._make_session({"track_filepaths": [P_TRACK]})
        app_info_cache.set("last_playback_session", session)

        _session_directory(P_ARTIST, P_ARTIST2)

        stored = app_info_cache.get("last_playback_session")
        assert any("Artist2" in f for f in stored["descriptor"]["track_filepaths"])

    def test_no_descriptor_key_does_not_raise(self):
        from utils.app_info_cache import app_info_cache
        from utils.filepath_update import _session_file

        session = {"current_track_filepath": P_TRACK, "resolved_tracks": []}
        app_info_cache.set("last_playback_session", session)

        _session_file(P_TRACK, P_TRACK_NEW)  # must not raise


# ---------------------------------------------------------------------------
# Gap #3: _db_dir_json_file — same-dir rename and cross-dir move
# ---------------------------------------------------------------------------

class TestDbDirJsonFile:
    def test_same_dir_rename_replaces_path_in_files(self, isolated_db):
        conn = isolated_db
        conn.execute(
            "INSERT INTO directories VALUES (?, ?, ?)",
            (P_ALBUM, json.dumps([P_TRACK]), 1.0),
        )
        conn.commit()

        from utils.filepath_update import _db_dir_json_file
        _db_dir_json_file(P_TRACK, P_TRACK_NEW)

        files = _dir_files(conn, P_ALBUM)
        assert P_TRACK_NEW in files
        assert P_TRACK not in files

    def test_cross_dir_removes_from_source(self, isolated_db):
        conn = isolated_db
        conn.execute(
            "INSERT INTO directories VALUES (?, ?, ?)",
            (P_ALBUM, json.dumps([P_TRACK]), 1.0),
        )
        conn.execute("INSERT INTO directories VALUES (?, ?, ?)", (P_ALBUM2, "[]", 1.0))
        conn.commit()

        from utils.filepath_update import _db_dir_json_file
        _db_dir_json_file(P_TRACK, P_TRACK_XDIR)

        files = _dir_files(conn, P_ALBUM)
        assert P_TRACK not in files

    def test_cross_dir_appends_to_existing_dest_row(self, isolated_db):
        conn = isolated_db
        other = "/music/Artist/Album2/other.flac"
        conn.execute(
            "INSERT INTO directories VALUES (?, ?, ?)",
            (P_ALBUM, json.dumps([P_TRACK]), 1.0),
        )
        conn.execute(
            "INSERT INTO directories VALUES (?, ?, ?)",
            (P_ALBUM2, json.dumps([other]), 1.0),
        )
        conn.commit()

        from utils.filepath_update import _db_dir_json_file
        _db_dir_json_file(P_TRACK, P_TRACK_XDIR)

        files = _dir_files(conn, P_ALBUM2)
        assert P_TRACK_XDIR in files
        assert other in files

    def test_cross_dir_creates_missing_dest_row(self, isolated_db):
        conn = isolated_db
        conn.execute(
            "INSERT INTO directories VALUES (?, ?, ?)",
            (P_ALBUM, json.dumps([P_TRACK]), 1.0),
        )
        conn.commit()
        # P_ALBUM2 has no directories row yet

        from utils.filepath_update import _db_dir_json_file
        _db_dir_json_file(P_TRACK, P_TRACK_XDIR)

        files = _dir_files(conn, P_ALBUM2)
        assert files is not None
        assert P_TRACK_XDIR in files

    def test_cross_dir_no_duplicate_in_dest(self, isolated_db):
        conn = isolated_db
        conn.execute(
            "INSERT INTO directories VALUES (?, ?, ?)",
            (P_ALBUM, json.dumps([P_TRACK]), 1.0),
        )
        conn.execute(
            "INSERT INTO directories VALUES (?, ?, ?)",
            (P_ALBUM2, json.dumps([P_TRACK_XDIR]), 1.0),
        )
        conn.commit()

        from utils.filepath_update import _db_dir_json_file
        _db_dir_json_file(P_TRACK, P_TRACK_XDIR)

        files = _dir_files(conn, P_ALBUM2)
        assert files.count(P_TRACK_XDIR) == 1


# ---------------------------------------------------------------------------
# Gap #3: _lib_file — DIRECTORIES_CACHE updates (no DB fixture needed)
# ---------------------------------------------------------------------------

class TestLibFileCross:
    def test_same_dir_rename_updates_cache_entry(self):
        from library_data.library_data import LibraryData
        from utils.filepath_update import _lib_file

        LibraryData.DIRECTORIES_CACHE[P_ALBUM] = [P_TRACK]

        _lib_file(P_TRACK, P_TRACK_NEW)

        files = LibraryData.DIRECTORIES_CACHE[P_ALBUM]
        assert P_TRACK_NEW in files
        assert P_TRACK not in files

    def test_cross_dir_removes_from_source_cache(self):
        from library_data.library_data import LibraryData
        from utils.filepath_update import _lib_file

        LibraryData.DIRECTORIES_CACHE[P_ALBUM] = [P_TRACK]
        LibraryData.DIRECTORIES_CACHE[P_ALBUM2] = []

        _lib_file(P_TRACK, P_TRACK_XDIR)

        assert P_TRACK not in LibraryData.DIRECTORIES_CACHE[P_ALBUM]

    def test_cross_dir_appends_to_existing_dest_cache(self):
        from library_data.library_data import LibraryData
        from utils.filepath_update import _lib_file

        other = "/music/Artist/Album2/other.flac"
        LibraryData.DIRECTORIES_CACHE[P_ALBUM] = [P_TRACK]
        LibraryData.DIRECTORIES_CACHE[P_ALBUM2] = [other]

        _lib_file(P_TRACK, P_TRACK_XDIR)

        files = LibraryData.DIRECTORIES_CACHE[P_ALBUM2]
        assert P_TRACK_XDIR in files
        assert other in files

    def test_cross_dir_creates_dest_cache_entry_when_absent(self):
        from library_data.library_data import LibraryData
        from utils.filepath_update import _lib_file

        LibraryData.DIRECTORIES_CACHE[P_ALBUM] = [P_TRACK]
        # P_ALBUM2 deliberately absent

        _lib_file(P_TRACK, P_TRACK_XDIR)

        assert P_ALBUM2 in LibraryData.DIRECTORIES_CACHE
        assert P_TRACK_XDIR in LibraryData.DIRECTORIES_CACHE[P_ALBUM2]


# ---------------------------------------------------------------------------
# propagate_file_delete helpers
# ---------------------------------------------------------------------------

class TestDbFileDelete:
    def test_removes_track_row(self, isolated_db):
        conn = isolated_db
        conn.execute(
            "INSERT INTO media_tracks (filepath, title, scanned_at) VALUES (?, ?, ?)",
            (P_TRACK, "My Track", 1.0),
        )
        conn.commit()

        from utils.filepath_update import _db_file_delete
        _db_file_delete(P_TRACK)

        row = conn.execute(
            "SELECT * FROM media_tracks WHERE filepath=?", (P_TRACK,)
        ).fetchone()
        assert row is None

    def test_no_row_does_not_raise(self, isolated_db):
        from utils.filepath_update import _db_file_delete
        _db_file_delete("/nonexistent/track.flac")  # must not raise


class TestDbDirJsonFileDelete:
    def test_removes_filepath_from_files_json(self, isolated_db):
        conn = isolated_db
        other = "/music/Artist/Album/other.flac"
        conn.execute(
            "INSERT INTO directories VALUES (?, ?, ?)",
            (P_ALBUM, json.dumps([P_TRACK, other]), 1.0),
        )
        conn.commit()

        from utils.filepath_update import _db_dir_json_file_delete
        _db_dir_json_file_delete(P_TRACK)

        files = _dir_files(conn, P_ALBUM)
        assert P_TRACK not in files
        assert other in files

    def test_no_directory_row_does_not_raise(self, isolated_db):
        from utils.filepath_update import _db_dir_json_file_delete
        _db_dir_json_file_delete(P_TRACK)  # no row in DB — must not raise


class TestLibFileDelete:
    def test_removes_from_media_track_cache(self):
        from types import SimpleNamespace
        from library_data.library_data import LibraryData
        from utils.filepath_update import _lib_file_delete

        track = SimpleNamespace(filepath=P_TRACK)
        LibraryData.MEDIA_TRACK_CACHE[P_TRACK] = track

        _lib_file_delete(P_TRACK)

        assert P_TRACK not in LibraryData.MEDIA_TRACK_CACHE

    def test_removes_from_all_tracks(self):
        from types import SimpleNamespace
        from library_data.library_data import LibraryData
        from utils.filepath_update import _lib_file_delete

        track = SimpleNamespace(filepath=P_TRACK)
        LibraryData.all_tracks = [track]

        _lib_file_delete(P_TRACK)

        assert track not in LibraryData.all_tracks

    def test_removes_from_directories_cache(self):
        from library_data.library_data import LibraryData
        from utils.filepath_update import _lib_file_delete

        other = "/music/Artist/Album/other.flac"
        LibraryData.DIRECTORIES_CACHE[P_ALBUM] = [P_TRACK, other]

        _lib_file_delete(P_TRACK)

        assert P_TRACK not in LibraryData.DIRECTORIES_CACHE[P_ALBUM]
        assert other in LibraryData.DIRECTORIES_CACHE[P_ALBUM]

    def test_absent_path_is_noop(self):
        from library_data.library_data import LibraryData
        from utils.filepath_update import _lib_file_delete

        LibraryData.DIRECTORIES_CACHE[P_ALBUM] = ["/other/track.flac"]

        _lib_file_delete(P_TRACK)  # must not raise or mutate unrelated entries

        assert "/other/track.flac" in LibraryData.DIRECTORIES_CACHE[P_ALBUM]


class TestPlaylistFileDelete:
    def test_removes_from_recently_played_filepaths(self):
        from muse.playlist import Playlist
        from utils.filepath_update import _playlist_file_delete

        Playlist.recently_played_filepaths = [P_TRACK, P_TRACK_NEW]

        _playlist_file_delete(P_TRACK)

        assert P_TRACK not in Playlist.recently_played_filepaths
        assert P_TRACK_NEW in Playlist.recently_played_filepaths

    def test_persists_removal_to_app_info_cache(self):
        from muse.playlist import Playlist
        from utils.app_info_cache import app_info_cache
        from utils.globals import HistoryType
        from utils.filepath_update import _playlist_file_delete

        key = HistoryType.TRACKS.value
        app_info_cache.set(key, [P_TRACK, P_TRACK_NEW])
        Playlist.recently_played_filepaths = [P_TRACK, P_TRACK_NEW]

        _playlist_file_delete(P_TRACK)

        assert P_TRACK not in app_info_cache.get(key, [])
        assert P_TRACK_NEW in app_info_cache.get(key, [])


class TestSessionFileDelete:
    def _make_session(self, current=P_TRACK, resolved=None, desc=None):
        return {
            "current_track_filepath": current,
            "resolved_tracks": resolved or [P_TRACK],
            "descriptor": desc or {},
        }

    def test_clears_current_track_filepath_when_matched(self):
        from utils.app_info_cache import app_info_cache
        from utils.filepath_update import _session_file_delete

        app_info_cache.set("last_playback_session", self._make_session())

        _session_file_delete(P_TRACK)

        stored = app_info_cache.get("last_playback_session")
        assert stored["current_track_filepath"] == ""

    def test_leaves_current_track_filepath_when_different(self):
        from utils.app_info_cache import app_info_cache
        from utils.filepath_update import _session_file_delete

        other = "/music/other.flac"
        app_info_cache.set("last_playback_session", self._make_session(current=other))

        _session_file_delete(P_TRACK)

        stored = app_info_cache.get("last_playback_session")
        assert stored["current_track_filepath"] == other

    def test_removes_from_resolved_tracks(self):
        from utils.app_info_cache import app_info_cache
        from utils.filepath_update import _session_file_delete

        session = self._make_session(resolved=[P_TRACK, P_TRACK_NEW])
        app_info_cache.set("last_playback_session", session)

        _session_file_delete(P_TRACK)

        stored = app_info_cache.get("last_playback_session")
        assert P_TRACK not in stored["resolved_tracks"]
        assert P_TRACK_NEW in stored["resolved_tracks"]

    def test_removes_from_descriptor_track_filepaths(self):
        from utils.app_info_cache import app_info_cache
        from utils.filepath_update import _session_file_delete

        desc = {"track_filepaths": [P_TRACK, P_TRACK_NEW]}
        app_info_cache.set("last_playback_session", self._make_session(desc=desc))

        _session_file_delete(P_TRACK)

        stored = app_info_cache.get("last_playback_session")
        assert P_TRACK not in stored["descriptor"]["track_filepaths"]
        assert P_TRACK_NEW in stored["descriptor"]["track_filepaths"]

    def test_no_session_does_not_raise(self):
        from utils.filepath_update import _session_file_delete
        _session_file_delete(P_TRACK)  # no session set — must not raise


class TestFavoritesFileDelete:
    def test_removes_matching_favorite(self):
        from utils.app_info_cache import app_info_cache
        from utils.filepath_update import _favorites_file_delete

        favs = [{"filepath": P_TRACK, "title": "My Track"}, {"filepath": P_TRACK_NEW}]
        app_info_cache.set("favorites", favs)

        _favorites_file_delete(P_TRACK)

        stored = app_info_cache.get("favorites", [])
        assert not any(f.get("filepath") == P_TRACK for f in stored)
        assert any(f.get("filepath") == P_TRACK_NEW for f in stored)

    def test_no_match_leaves_favorites_unchanged(self):
        from utils.app_info_cache import app_info_cache
        from utils.filepath_update import _favorites_file_delete

        favs = [{"filepath": P_TRACK_NEW}]
        app_info_cache.set("favorites", favs)

        _favorites_file_delete(P_TRACK)

        stored = app_info_cache.get("favorites", [])
        assert len(stored) == 1


class TestPlaylistDescriptorsFileDelete:
    def test_removes_from_playlist_descriptor(self):
        from utils.app_info_cache import app_info_cache
        from utils.filepath_update import _playlist_descriptors_file_delete

        desc = {"track_filepaths": [P_TRACK, P_TRACK_NEW]}
        app_info_cache.set("playlist_descriptors", {"list_a": desc})

        _playlist_descriptors_file_delete(P_TRACK)

        raw = app_info_cache.get("playlist_descriptors", {})
        assert P_TRACK not in raw["list_a"]["track_filepaths"]
        assert P_TRACK_NEW in raw["list_a"]["track_filepaths"]

    def test_removes_from_recent_descriptor(self):
        from utils.app_info_cache import app_info_cache
        from utils.filepath_update import _playlist_descriptors_file_delete

        recent = [{"track_filepaths": [P_TRACK, P_TRACK_NEW]}]
        app_info_cache.set("recent_playlist_descriptors", recent)

        _playlist_descriptors_file_delete(P_TRACK)

        stored = app_info_cache.get("recent_playlist_descriptors", [])
        assert P_TRACK not in stored[0]["track_filepaths"]
        assert P_TRACK_NEW in stored[0]["track_filepaths"]

    def test_no_match_does_not_mutate(self):
        from utils.app_info_cache import app_info_cache
        from utils.filepath_update import _playlist_descriptors_file_delete

        desc = {"track_filepaths": [P_TRACK_NEW]}
        app_info_cache.set("playlist_descriptors", {"list_a": desc})

        _playlist_descriptors_file_delete(P_TRACK)

        raw = app_info_cache.get("playlist_descriptors", {})
        assert raw["list_a"]["track_filepaths"] == [P_TRACK_NEW]
