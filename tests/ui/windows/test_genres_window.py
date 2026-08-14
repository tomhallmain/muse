"""Genres window tests (isolated metadata / DB)."""

import pytest
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt

from library_data.genre import GenresDataSearch
from tests.utils.qt_test_helpers import process_events_for


@pytest.mark.ui
class TestGenresWindow:
    def test_opens(self, qapp, qt_master, mock_app_actions):
        from ui_qt.genres_window import GenresWindow

        win = GenresWindow(qt_master, mock_app_actions)
        process_events_for(0.3)
        assert win.isVisible()
        win.close()

    def test_search_baroque_in_seeded_genres(self, qapp, qt_master, mock_app_actions):
        from library_data.genre import genre_data
        from ui_qt.genres_window import GenresWindow

        search = GenresDataSearch(genre="baroque")
        genre_data.do_search(search)
        assert len(search.get_results()) > 0

        win = GenresWindow(qt_master, mock_app_actions)
        process_events_for(0.3)
        win.genre_entry.setText("baroque")
        QTest.mouseClick(win.search_btn, Qt.MouseButton.LeftButton)
        process_events_for(0.5)
        assert win.genre_data_search is not None
        assert len(win.genre_data_search.get_results()) > 0
        win.close()

    def test_list_all_genres(self, qapp, qt_master, mock_app_actions):
        from ui_qt.genres_window import GenresWindow

        win = GenresWindow(qt_master, mock_app_actions)
        process_events_for(0.3)
        QTest.mouseClick(win.list_all_btn, Qt.MouseButton.LeftButton)
        process_events_for(0.5)
        assert win.genre_data_search is not None
        assert len(win.genre_data_search.get_results()) > 0
        win.close()

    def test_recent_genre_searches_stored_in_app_info_cache(
        self, qapp, qt_master, mock_app_actions, isolated_singletons
    ):
        from library_data.genre import genre_data
        from ui_qt.genres_window import GenresWindow
        from utils.app_info_cache import app_info_cache

        search = GenresDataSearch(genre="baroque")
        genre_data.do_search(search)
        search.set_stored_results_count()
        GenresWindow.recent_searches = [search]
        GenresWindow.store_recent_searches()
        app_info_cache.store()

        GenresWindow.recent_searches = []
        GenresWindow.load_recent_searches()
        assert len(GenresWindow.recent_searches) >= 1
        assert GenresWindow.recent_searches[0].genre == "baroque"

    def test_close_persists_and_reopen_restores_recent_search(
        self, qapp, qt_master, mock_app_actions, isolated_singletons
    ):
        """GenresWindow wires load/store into __init__/closeEvent (unlike Forms/
        Composers, which define both but never call either). Covers that
        wiring through the real window lifecycle rather than calling the two
        staticmethods directly.
        """
        from ui_qt.genres_window import GenresWindow

        GenresWindow.recent_searches = []

        win = GenresWindow(qt_master, mock_app_actions)
        process_events_for(0.3)
        win.genre_entry.setText("baroque")
        QTest.mouseClick(win.search_btn, Qt.MouseButton.LeftButton)
        process_events_for(0.5)
        win.close()
        process_events_for(0.1)

        GenresWindow.recent_searches = []
        win2 = GenresWindow(qt_master, mock_app_actions)
        process_events_for(0.3)
        assert any(s.genre == "baroque" for s in GenresWindow.recent_searches)
        win2.close()
