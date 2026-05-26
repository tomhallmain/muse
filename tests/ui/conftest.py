"""
Qt / PySide6 test harness.

Env bootstrap lives in ``tests/conftest.py`` (not duplicated here).
See ``tests/docs/DATA_CACHE_ISOLATION.md`` for metadata JSON and cache isolation.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from tests.utils.metadata_isolation import (
    apply_metadata_paths_to_config,
    copy_example_metadata_to,
    reload_metadata_singletons,
)
from tests.utils.ui_window_helpers import (
    make_mock_app_actions,
    make_qt_master,
    seed_library_data_from_tracks,
)

pytestmark = pytest.mark.ui


@pytest.fixture(scope="session")
def qapp():
    """Single ``QApplication`` for the UI test session."""
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    yield instance


@pytest.fixture
def qt_master(qapp):
    master = make_qt_master(qapp)
    yield master
    master.close()
    qapp.processEvents()


@pytest.fixture
def mock_app_actions():
    return make_mock_app_actions()


@pytest.fixture(autouse=True)
def bypass_multi_display_positioning(monkeypatch):
    """Avoid ``QWidget.screen()`` during SmartWindow construction (Windows/offscreen)."""
    from tests.utils.qt_display_test_bypass import install_display_position_bypass

    install_display_position_bypass(monkeypatch)


@pytest.fixture(autouse=True)
def isolated_metadata_files(tmp_path, monkeypatch):
    """Writable copies of example metadata JSON; reload data singletons."""
    import importlib

    import utils
    from utils.config import Config

    config_module = importlib.import_module("utils.config")
    config_instance = (
        utils.config
        if isinstance(utils.config, Config)
        else config_module.config
    )

    paths = copy_example_metadata_to(tmp_path / "metadata")
    apply_metadata_paths_to_config(config_instance, paths)
    reload_metadata_singletons(monkeypatch)
    yield paths


@pytest.fixture
def fixture_library_data(audio_library_media_tracks, audio_library_dir):
    return seed_library_data_from_tracks(
        audio_library_media_tracks,
        audio_library_dir,
    )


@pytest.fixture(autouse=True)
def reset_ui_window_state():
    """Clear class-level UI lists so tests do not share recent searches/favorites."""
    from ui_qt.composers_window import ComposersWindow
    from ui_qt.favorites_window import FavoritesWindow
    from ui_qt.history_window import HistoryWindow
    from ui_qt.library_window import LibraryWindow
    from ui_qt.playlist_window import MasterPlaylistWindow
    from ui_qt.search_window import SearchWindow

    SearchWindow.recent_searches = []
    SearchWindow.top_level = None
    FavoritesWindow.recent_favorites = []
    FavoritesWindow.top_level = None
    ComposersWindow.recent_searches = []
    ComposersWindow.top_level = None
    ComposersWindow.details_window = None
    HistoryWindow.top_level = None
    LibraryWindow.top_level = None
    MasterPlaylistWindow.top_level = None

    from muse.playback_config_master import PlaybackConfigMaster
    from muse.playback_state import PlaybackStateManager

    PlaybackStateManager.reset()
    PlaybackConfigMaster.open_configs.clear()

    yield

    PlaybackStateManager.reset()
    PlaybackConfigMaster.open_configs.clear()
    SearchWindow.recent_searches = []
    SearchWindow.top_level = None
    FavoritesWindow.recent_favorites = []
    FavoritesWindow.top_level = None
    ComposersWindow.recent_searches = []
    ComposersWindow.top_level = None
    ComposersWindow.details_window = None
    HistoryWindow.top_level = None
    LibraryWindow.top_level = None
    MasterPlaylistWindow.top_level = None
