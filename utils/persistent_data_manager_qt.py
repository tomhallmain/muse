"""
Persistent data manager for the PySide6 (Qt) UI context.

Load/store populates ui_qt window class-level data (e.g. SearchWindow.recent_searches)
so that the Qt app sees recent searches, favorites, etc. Use this in app_qt.py
instead of PersistentDataManager, which loads into the Tkinter (ui) window classes.
"""

from extensions.extension_manager import ExtensionManager
from library_data.library_data import LibraryData
from muse.muse_memory import muse_memory
from muse.playlist import Playlist
from muse.schedules_manager import SchedulesManager
from ui_qt.composers_window import ComposersWindow
from ui_qt.favorites_window import FavoritesWindow
from ui_qt.playlist_window import MasterPlaylistWindow
from ui_qt.search_window import SearchWindow
from utils.audio_device_manager import AudioDeviceManager


class PersistentDataManagerQt:
    """Load/store persistent data into ui_qt window classes (for use by app_qt)."""

    _is_loaded = False

    @staticmethod
    def store():
        muse_memory.save()
        LibraryData.store_caches()
        Playlist.store_recently_played_lists()
        MasterPlaylistWindow.store_named_playlist_configs()
        SchedulesManager.store_schedules()
        ExtensionManager.store_extensions()
        SearchWindow.store_recent_searches()
        ComposersWindow.store_recent_searches()
        FavoritesWindow.store_favorites()
        AudioDeviceManager.store_settings()

    @staticmethod
    def load():
        if PersistentDataManagerQt._is_loaded:
            return

        muse_memory.load()
        LibraryData.load_directory_cache()
        LibraryData.load_media_track_cache()
        Playlist.load_recently_played_lists()
        MasterPlaylistWindow.load_named_playlist_configs()
        SchedulesManager.set_schedules()
        ExtensionManager.load_extensions()
        SearchWindow.load_recent_searches()
        ComposersWindow.load_recent_searches()
        FavoritesWindow.load_favorites()
        AudioDeviceManager.load_settings()

        PersistentDataManagerQt._is_loaded = True
