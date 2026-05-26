"""Composers window tests (isolated metadata JSON copies)."""

import pytest
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt

from library_data.composer import ComposersDataSearch
from tests.utils.qt_test_helpers import process_events_for


@pytest.mark.ui
class TestComposersWindow:
    def test_opens(self, qapp, qt_master, mock_app_actions):
        from ui_qt.composers_window import ComposersWindow

        win = ComposersWindow(qt_master, mock_app_actions)
        process_events_for(0.3)
        assert win.isVisible()
        win.close()

    def test_search_beethoven_in_example_metadata(self, qapp, qt_master, mock_app_actions):
        from library_data.composer import composers_data
        from ui_qt.composers_window import ComposersWindow

        search = ComposersDataSearch(composer="beethoven")
        composers_data.do_search(search)
        assert len(search.get_results()) > 0

        win = ComposersWindow(qt_master, mock_app_actions)
        win.composer_entry.setText("beethoven")
        QTest.mouseClick(win.search_btn, Qt.MouseButton.LeftButton)
        process_events_for(0.5)
        assert win.composer_data_search is not None
        assert len(win.composer_data_search.get_results()) > 0
        win.close()

    def test_recent_composer_searches_stored_in_app_info_cache(
        self, qapp, qt_master, mock_app_actions, isolated_singletons
    ):
        from ui_qt.composers_window import ComposersWindow
        from utils.app_info_cache import app_info_cache

        from library_data.composer import composers_data

        search = ComposersDataSearch(composer="bach")
        composers_data.do_search(search)
        search.set_stored_results_count()
        ComposersWindow.recent_searches = [search]
        ComposersWindow.store_recent_searches()
        app_info_cache.store()

        ComposersWindow.recent_searches = []
        ComposersWindow.load_recent_searches()
        assert len(ComposersWindow.recent_searches) >= 1
        assert ComposersWindow.recent_searches[0].composer == "bach"

    def test_genre_search_in_example_metadata(self, qapp, qt_master, mock_app_actions):
        from library_data.composer import composers_data
        from ui_qt.composers_window import ComposersWindow

        search = ComposersDataSearch(genre="classical")
        composers_data.do_search(search)
        assert len(search.get_results()) > 0

        win = ComposersWindow(qt_master, mock_app_actions)
        win.genre_entry.setText("classical")
        QTest.mouseClick(win.search_btn, Qt.MouseButton.LeftButton)
        process_events_for(0.5)
        assert len(win.composer_data_search.get_results()) > 0
        win.close()
