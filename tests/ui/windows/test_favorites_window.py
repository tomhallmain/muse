"""Favorites window tests (app_info_cache backed, isolated per test)."""

import pytest

from library_data.favorite import Favorite
from utils.globals import TrackAttribute
from tests.utils.qt_test_helpers import process_events_for


@pytest.mark.ui
class TestFavoritesWindow:
    def test_opens_empty(self, qapp, qt_master, mock_app_actions, fixture_library_data):
        from ui_qt.favorites_window import FavoritesWindow

        FavoritesWindow.recent_favorites = []
        win = FavoritesWindow(qt_master, mock_app_actions, fixture_library_data)
        process_events_for(0.3)
        assert win.isVisible()
        win.close()

    def test_store_and_reload_favorites_roundtrip(
        self,
        qapp,
        qt_master,
        mock_app_actions,
        fixture_library_data,
        audio_library_media_tracks,
        isolated_singletons,
    ):
        from ui_qt.favorites_window import FavoritesWindow
        from utils.app_info_cache import app_info_cache

        track = audio_library_media_tracks[0]
        fav = Favorite.from_track(track)
        FavoritesWindow.recent_favorites = [fav]
        FavoritesWindow.store_favorites()
        app_info_cache.store()

        FavoritesWindow.recent_favorites = []
        FavoritesWindow.load_favorites()
        assert len(FavoritesWindow.recent_favorites) == 1
        assert FavoritesWindow.recent_favorites[0].value == fav.value
        assert FavoritesWindow.recent_favorites[0].filepath == track.filepath

        win = FavoritesWindow(qt_master, mock_app_actions, fixture_library_data)
        process_events_for(0.2)
        assert win.isVisible()
        win.close()

    def test_search_filters_loaded_favorites(
        self, qapp, qt_master, mock_app_actions, fixture_library_data, audio_library_media_tracks
    ):
        from ui_qt.favorites_window import FavoritesWindow

        track = audio_library_media_tracks[0]
        FavoritesWindow.recent_favorites = [Favorite.from_track(track)]
        win = FavoritesWindow(qt_master, mock_app_actions, fixture_library_data)
        term = (track.title or "symphony")[:6].lower()
        win.favorite_entry.setText(term)
        win.do_search()
        process_events_for(0.3)
        assert len(win.favorite_data_search.get_results()) > 0
        win.close()
