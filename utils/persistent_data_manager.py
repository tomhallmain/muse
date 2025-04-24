
from extensions.extension_manager import ExtensionManager
from library_data.library_data import LibraryData
from muse.muse_memory import MuseMemory
from muse.playlist import Playlist
from muse.schedules_manager import SchedulesManager
from ui.composers_window import ComposersWindow
from ui.playlist_window import MasterPlaylistWindow
from ui.search_window import SearchWindow


class PersistentDataManager:
    @staticmethod
    def store():
        MuseMemory.save()
        LibraryData.store_caches()
        Playlist.store_recently_played_lists()
        MasterPlaylistWindow.store_named_playlist_configs()
        SchedulesManager.store_schedules()
        ExtensionManager.store_extensions()
        SearchWindow.store_recent_searches()
        ComposersWindow.store_recent_searches()

    @staticmethod
    def load():
        MuseMemory.load()
        LibraryData.load_directory_cache()
        LibraryData.load_media_track_cache()
        Playlist.load_recently_played_lists()
        MasterPlaylistWindow.load_named_playlist_configs()
        SchedulesManager.set_schedules()
        ExtensionManager.load_extensions()
        SearchWindow.load_recent_searches()
        ComposersWindow.load_recent_searches()

