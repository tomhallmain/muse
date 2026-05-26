"""Helpers to open Qt windows in tests with stub callbacks and seeded library data."""

from __future__ import annotations

import time
from typing import Callable, Optional

from PySide6.QtWidgets import QApplication, QWidget

from tests.utils.qt_test_helpers import process_events_for


def make_mock_app_actions() -> "AppActions":
    from ui_qt.app_actions import AppActions

    def _noop(*_a, **_k):
        return None

    actions = {name: _noop for name in AppActions.REQUIRED_ACTIONS}
    actions["get_current_track"] = lambda: None
    actions["get_media_volume"] = lambda: 0
    actions["is_media_muted"] = lambda: False
    return AppActions(actions, master=None)


def make_qt_master(qapp: QApplication) -> QWidget:
    master = QWidget()
    master.setWindowTitle("Muse test host")
    master.resize(200, 200)
    return master


def _get_config_instance():
    import importlib

    import utils
    from utils.config import Config

    config_module = importlib.import_module("utils.config")
    if isinstance(utils.config, Config):
        return utils.config
    return config_module.config


def seed_library_data_from_tracks(tracks, audio_library_dir) -> "LibraryData":
    """Populate class caches so ``LibraryData.do_search`` sees fixture tracks only."""
    from library_data.library_data import LibraryData

    LibraryData.MEDIA_TRACK_CACHE = {t.filepath: t for t in tracks}
    LibraryData.all_tracks = list(tracks)
    LibraryData.DIRECTORIES_CACHE = {}
    LibraryData._directory_cache_loaded = True
    _get_config_instance().directories = [str(audio_library_dir)]
    return LibraryData(app_actions=make_mock_app_actions())


def wait_for_search_results(search_win, timeout: float = 15.0) -> int:
    """Process Qt events until the search window has result rows."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.05)
        search = getattr(search_win, "library_data_search", None)
        if search is not None and len(search.get_results()) > 0 and len(search_win.title_list) > 0:
            return len(search.get_results())
    return 0


def build_fixture_playback_master(
    callbacks,
    num_tracks: int = 12,
    advance: int = 3,
):
    """Build a ``PlaybackConfigMaster`` on fixture tracks and register it as active."""
    from muse.playback_config import PlaybackConfig
    from muse.playback_config_master import PlaybackConfigMaster
    from muse.playback_state import PlaybackStateManager
    from muse.playlist import Playlist
    from muse.sort_config import SortConfig

    tracks = callbacks.get_all_tracks()[:num_tracks]
    filepaths = [t.filepath for t in tracks]
    sort_config = SortConfig(skip_memory_shuffle=True, skip_random_start=True)
    playlist = Playlist(
        tracks=filepaths,
        data_callbacks=callbacks,
        sort_config=sort_config,
    )
    pc = PlaybackConfig(data_callbacks=callbacks)
    pc.list = playlist
    master = PlaybackConfigMaster([pc])
    for _ in range(advance):
        master.next_track()
    PlaybackStateManager.set_active_config(master)
    return master, pc


def run_search_sync(search_win, overwrite: bool = False) -> int:
    """Run search on the UI thread (bypass worker) and refresh widgets."""
    assert search_win.library_data_search is not None
    search_win.library_data.do_search(
        search_win.library_data_search,
        overwrite=overwrite,
    )
    search_win._update_ui_after_search()
    search_win._refresh_widgets()
    process_events_for(0.2)
    return len(search_win.library_data_search.get_results())
