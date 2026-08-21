"""End-to-end album deletion: real folders on disk, real DB rows, real caches.

Exercises ``MuseAppQt.delete_album`` as an unbound method against a minimal
stand-in, so the whole path -- library-root guard, rmtree, cache purge and
playlist pruning -- runs for real without booting Qt.
"""

import json
import os
import types

import pytest

from muse.playback_session import LAST_SESSION_KEY
from muse.playlist_descriptor import PLAYLIST_DESCRIPTORS_CACHE_KEY
from utils.db import get_connection

FAVORITES_KEY = "favorites"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

class _StubApp:
    """Exposes only what delete_album touches on the main window."""

    def __init__(self, current_track=None, current_run=None):
        from app_qt import MuseAppQt

        self.alerts = []
        self._current_track = current_track
        self.current_run = current_run
        for name in ("_skip_playback_if_doomed", "_purge_from_active_playlist"):
            setattr(self, name, types.MethodType(getattr(MuseAppQt, name), self))

    def alert(self, title, message, kind="info", **kwargs):
        self.alerts.append((title, message))

    def get_current_track(self):
        return self._current_track


class _StubTrack:
    def __init__(self, filepath):
        self.filepath = filepath


class _StubRun:
    def __init__(self):
        self.is_started = True
        self.is_complete = False
        self.next_calls = 0

    def next(self):
        self.next_calls += 1

    def get_playback(self):
        return types.SimpleNamespace(
            _playback_config=types.SimpleNamespace(get_list=lambda: None)
        )


def _delete_album(stub, album_dir):
    from app_qt import MuseAppQt

    return MuseAppQt.delete_album(stub, album_dir)


def _write_album(root, name, track_names, extras=()):
    """Create an album folder on disk. Returns (album_dir, [track paths])."""
    album_dir = root / name
    album_dir.mkdir(parents=True)
    track_paths = []
    for track_name in track_names:
        path = album_dir / track_name
        path.write_bytes(b"\0" * 32)
        track_paths.append(str(path))
    for extra in extras:
        (album_dir / extra).write_bytes(b"\0")
    return str(album_dir), track_paths


@pytest.fixture
def library(tmp_path, monkeypatch, app_info_cache):
    """Two albums under one artist folder, registered in the DB and every cache."""
    from library_data.library_data import LibraryData

    root = tmp_path / "music"
    artist_dir = root / "Artist"
    doomed_dir, doomed_tracks = _write_album(
        artist_dir, "Album", ["01.mp3", "02.mp3"], extras=["cover.jpg"]
    )
    kept_dir, kept_tracks = _write_album(artist_dir, "Album2", ["01.mp3"])

    conn = get_connection()
    for path in doomed_tracks + kept_tracks:
        conn.execute(
            "INSERT INTO media_tracks (filepath, parent_filepath, title, scanned_at) "
            "VALUES (?, ?, ?, ?)",
            (path, os.path.dirname(path), os.path.basename(path), 1.0),
        )
    conn.execute(
        "INSERT INTO directories (path, files, scanned_at) VALUES (?, ?, ?)",
        (doomed_dir, json.dumps(doomed_tracks), 1.0),
    )
    conn.execute(
        "INSERT INTO directories (path, files, scanned_at) VALUES (?, ?, ?)",
        (kept_dir, json.dumps(kept_tracks), 1.0),
    )
    conn.execute(
        "INSERT INTO directories (path, files, scanned_at) VALUES (?, ?, ?)",
        (str(artist_dir), json.dumps(doomed_tracks + kept_tracks), 1.0),
    )
    conn.commit()

    all_tracks = [_StubTrack(p) for p in doomed_tracks + kept_tracks]
    LibraryData.MEDIA_TRACK_CACHE = {t.filepath: t for t in all_tracks}
    LibraryData.all_tracks = list(all_tracks)
    LibraryData.DIRECTORIES_CACHE = {
        doomed_dir: list(doomed_tracks),
        kept_dir: list(kept_tracks),
        str(artist_dir): doomed_tracks + kept_tracks,
    }

    app_info_cache.set(FAVORITES_KEY, [{"filepath": p} for p in doomed_tracks + kept_tracks])
    app_info_cache.set(LAST_SESSION_KEY, {
        "current_track_filepath": doomed_tracks[0],
        "resolved_tracks": doomed_tracks + kept_tracks,
        "descriptor": {
            "track_filepaths": doomed_tracks + kept_tracks,
            "source_directories": [doomed_dir, kept_dir],
        },
    })
    app_info_cache.set(PLAYLIST_DESCRIPTORS_CACHE_KEY, {"list_a": {
        "track_filepaths": doomed_tracks + kept_tracks,
        "source_directories": [doomed_dir, kept_dir],
    }})

    # Patch the Config instance app_qt itself holds, so the library-root guard
    # reads the temp library rather than the developer's real directories.
    import app_qt

    monkeypatch.setattr(app_qt.config, "directories", [str(root)], raising=False)

    return types.SimpleNamespace(
        root=str(root), artist_dir=str(artist_dir),
        doomed_dir=doomed_dir, doomed_tracks=doomed_tracks,
        kept_dir=kept_dir, kept_tracks=kept_tracks,
    )


def _db_filepaths():
    return {r["filepath"] for r in get_connection().execute("SELECT filepath FROM media_tracks")}


def _db_dir_paths():
    return {r["path"] for r in get_connection().execute("SELECT path FROM directories")}


def _db_dir_files(path):
    row = get_connection().execute(
        "SELECT files FROM directories WHERE path=?", (path,)
    ).fetchone()
    return None if row is None else json.loads(row["files"])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestDeleteAlbumOnDisk:
    def test_removes_the_folder_and_everything_in_it(self, library):
        assert _delete_album(_StubApp(), library.doomed_dir) is True

        assert not os.path.exists(library.doomed_dir)
        assert os.path.exists(library.kept_dir)

    def test_missing_folder_reports_failure_without_raising(self, library):
        stub = _StubApp()
        missing = os.path.join(library.artist_dir, "NoSuchAlbum")

        assert _delete_album(stub, missing) is False
        assert len(stub.alerts) == 1


@pytest.mark.integration
class TestDeleteAlbumPurgesCaches:
    def test_db_rows_for_the_album_are_gone(self, library):
        _delete_album(_StubApp(), library.doomed_dir)

        remaining = _db_filepaths()
        assert remaining.isdisjoint(library.doomed_tracks)
        assert remaining.issuperset(library.kept_tracks)
        assert library.doomed_dir not in _db_dir_paths()
        assert library.kept_dir in _db_dir_paths()

    def test_parent_directory_row_keeps_only_surviving_files(self, library):
        _delete_album(_StubApp(), library.doomed_dir)

        assert _db_dir_files(library.artist_dir) == library.kept_tracks

    def test_library_data_caches_are_purged(self, library):
        from library_data.library_data import LibraryData

        _delete_album(_StubApp(), library.doomed_dir)

        assert set(LibraryData.MEDIA_TRACK_CACHE) == set(library.kept_tracks)
        assert [t.filepath for t in LibraryData.all_tracks] == library.kept_tracks
        assert library.doomed_dir not in LibraryData.DIRECTORIES_CACHE
        assert LibraryData.DIRECTORIES_CACHE[library.artist_dir] == library.kept_tracks

    def test_favorites_lose_the_deleted_tracks(self, library, app_info_cache):
        _delete_album(_StubApp(), library.doomed_dir)

        favs = [f["filepath"] for f in app_info_cache.get(FAVORITES_KEY, [])]
        assert favs == library.kept_tracks

    def test_session_and_descriptors_are_pruned(self, library, app_info_cache):
        _delete_album(_StubApp(), library.doomed_dir)

        session = app_info_cache.get(LAST_SESSION_KEY)
        assert session["current_track_filepath"] == ""
        assert session["resolved_tracks"] == library.kept_tracks
        assert session["descriptor"]["source_directories"] == [library.kept_dir]

        desc = app_info_cache.get(PLAYLIST_DESCRIPTORS_CACHE_KEY)["list_a"]
        assert desc["track_filepaths"] == library.kept_tracks
        assert desc["source_directories"] == [library.kept_dir]


@pytest.mark.integration
class TestDeleteAlbumLibraryRootGuard:
    def test_refuses_to_delete_a_configured_library_root(self, library):
        """A track sitting directly in a library root would otherwise take the
        whole library with it."""
        stub = _StubApp()

        assert _delete_album(stub, library.root) is False
        assert os.path.exists(library.root)
        assert len(stub.alerts) == 1

    def test_refuses_a_folder_that_contains_a_library_root(self, library):
        stub = _StubApp()
        above_root = os.path.dirname(library.root)

        assert _delete_album(stub, above_root) is False
        assert os.path.exists(library.root)

    def test_guard_leaves_caches_untouched(self, library):
        before = _db_filepaths()

        _delete_album(_StubApp(), library.root)

        assert _db_filepaths() == before


@pytest.mark.integration
class TestDeleteAlbumPlaybackHandling:
    def test_skips_playback_when_the_playing_track_is_in_the_folder(self, library):
        run = _StubRun()
        stub = _StubApp(current_track=_StubTrack(library.doomed_tracks[0]), current_run=run)

        _delete_album(stub, library.doomed_dir)

        assert run.next_calls == 1

    def test_leaves_playback_alone_when_playing_from_another_album(self, library):
        run = _StubRun()
        stub = _StubApp(current_track=_StubTrack(library.kept_tracks[0]), current_run=run)

        _delete_album(stub, library.doomed_dir)

        assert run.next_calls == 0

    def test_prunes_deleted_tracks_from_the_running_playlist(self, library):
        class _Playlist:
            def __init__(self, tracks):
                self.sorted_tracks = tracks

        playlist = _Playlist([_StubTrack(p) for p in library.doomed_tracks + library.kept_tracks])

        class _Run(_StubRun):
            def get_playback(self):
                return types.SimpleNamespace(
                    _playback_config=types.SimpleNamespace(get_list=lambda: playlist)
                )

        stub = _StubApp(current_run=_Run())

        _delete_album(stub, library.doomed_dir)

        assert [t.filepath for t in playlist.sorted_tracks] == library.kept_tracks
