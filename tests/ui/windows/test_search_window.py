"""Search window tests against the fixture audio library."""

import pytest
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt

from library_data.library_data import LibraryDataSearch
from tests.utils.qt_test_helpers import process_events_for
from tests.utils.ui_window_helpers import run_search_sync


@pytest.mark.ui
class TestSearchWindow:
    def test_opens_with_fixture_library(self, qapp, qt_master, mock_app_actions, fixture_library_data):
        from ui_qt.search_window import SearchWindow

        win = SearchWindow(qt_master, mock_app_actions, fixture_library_data)
        process_events_for(0.3)
        assert win.isVisible()
        assert win.library_data is fixture_library_data
        win.close()
        qapp.processEvents()

    def test_composer_search_finds_beethoven_tracks(
        self, qapp, qt_master, mock_app_actions, fixture_library_data
    ):
        from ui_qt.search_window import SearchWindow

        win = SearchWindow(qt_master, mock_app_actions, fixture_library_data)
        win.composer_entry.setText("beethoven")
        win.library_data_search = LibraryDataSearch(composer="beethoven", max_results=50)
        count = run_search_sync(win)
        assert count > 0
        composers = {t.composer for t in win.library_data_search.get_results()}
        assert any(c and "beethoven" in c.lower() for c in composers)
        win.close()

    def test_album_search_via_search_button(
        self, qapp, qt_master, mock_app_actions, fixture_library_data
    ):
        from ui_qt.search_window import SearchWindow

        win = SearchWindow(qt_master, mock_app_actions, fixture_library_data)
        win.album_entry.setText("Symphony")
        QTest.mouseClick(win.search_btn, Qt.MouseButton.LeftButton)
        process_events_for(2.0)
        assert win.library_data_search is not None
        assert len(win.library_data_search.get_results()) > 0
        win.close()

    def test_recent_search_stored_in_app_info_cache(
        self, qapp, qt_master, mock_app_actions, fixture_library_data, isolated_singletons
    ):
        from ui_qt.search_window import SearchWindow
        from utils.app_info_cache import app_info_cache

        search = LibraryDataSearch(composer="mozart", max_results=30)
        fixture_library_data.do_search(search)
        search.set_stored_results_count()
        SearchWindow.update_recent_searches(search)
        SearchWindow.store_recent_searches()
        app_info_cache.store()

        SearchWindow.recent_searches = []
        SearchWindow.load_recent_searches()
        assert len(SearchWindow.recent_searches) >= 1
        assert SearchWindow.recent_searches[0].composer == "mozart"

    def test_title_search_finds_symphony_tracks(
        self, qapp, qt_master, mock_app_actions, fixture_library_data
    ):
        from ui_qt.search_window import SearchWindow

        win = SearchWindow(qt_master, mock_app_actions, fixture_library_data)
        win.library_data_search = LibraryDataSearch(title="symphony", max_results=50)
        count = run_search_sync(win)
        assert count > 0
        assert any("symphony" in (t.title or "").lower() for t in win.library_data_search.get_results())
        win.close()
