"""Artists window tests (isolated metadata / DB)."""

import pytest
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt

from library_data.artist import ArtistsDataSearch
from tests.utils.qt_test_helpers import process_events_for


@pytest.mark.ui
class TestArtistsWindow:
    def test_opens(self, qapp, qt_master, mock_app_actions):
        from ui_qt.artists_window import ArtistsWindow

        win = ArtistsWindow(qt_master, mock_app_actions)
        process_events_for(0.3)
        assert win.isVisible()
        win.close()

    def test_search_allman_in_seeded_artists(self, qapp, qt_master, mock_app_actions):
        from library_data.artist import artists_data
        from ui_qt.artists_window import ArtistsWindow

        search = ArtistsDataSearch(artist="allman")
        artists_data.do_search(search)
        assert len(search.get_results()) > 0

        win = ArtistsWindow(qt_master, mock_app_actions)
        process_events_for(0.3)
        win.artist_entry.setText("allman")
        QTest.mouseClick(win.search_btn, Qt.MouseButton.LeftButton)
        process_events_for(0.5)
        assert win.artist_data_search is not None
        assert len(win.artist_data_search.get_results()) > 0
        win.close()

    def test_list_all_artists(self, qapp, qt_master, mock_app_actions):
        from ui_qt.artists_window import ArtistsWindow

        win = ArtistsWindow(qt_master, mock_app_actions)
        process_events_for(0.3)
        QTest.mouseClick(win.list_all_btn, Qt.MouseButton.LeftButton)
        process_events_for(0.5)
        assert win.artist_data_search is not None
        assert len(win.artist_data_search.get_results()) > 0
        win.close()

    def test_recent_artist_searches_stored_in_app_info_cache(
        self, qapp, qt_master, mock_app_actions, isolated_singletons
    ):
        from library_data.artist import artists_data
        from ui_qt.artists_window import ArtistsWindow
        from utils.app_info_cache import app_info_cache

        search = ArtistsDataSearch(artist="allman")
        artists_data.do_search(search)
        search.set_stored_results_count()
        ArtistsWindow.recent_searches = [search]
        ArtistsWindow.store_recent_searches()
        app_info_cache.store()

        ArtistsWindow.recent_searches = []
        ArtistsWindow.load_recent_searches()
        assert len(ArtistsWindow.recent_searches) >= 1
        assert ArtistsWindow.recent_searches[0].artist == "allman"

    def test_close_persists_and_reopen_restores_recent_search(
        self, qapp, qt_master, mock_app_actions, isolated_singletons
    ):
        """ArtistsWindow wires load/store into __init__/closeEvent, same as
        GenresWindow. Forms/Composers define both methods but never call
        either, so recent searches there don't survive a restart.
        """
        from ui_qt.artists_window import ArtistsWindow

        ArtistsWindow.recent_searches = []

        win = ArtistsWindow(qt_master, mock_app_actions)
        process_events_for(0.3)
        win.artist_entry.setText("allman")
        QTest.mouseClick(win.search_btn, Qt.MouseButton.LeftButton)
        process_events_for(0.5)
        win.close()
        process_events_for(0.1)

        ArtistsWindow.recent_searches = []
        win2 = ArtistsWindow(qt_master, mock_app_actions)
        process_events_for(0.3)
        assert any(s.artist == "allman" for s in ArtistsWindow.recent_searches)
        win2.close()
