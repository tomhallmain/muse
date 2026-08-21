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

    def test_excluded_result_play_button_disabled_with_tooltip(
        self, qapp, qt_master, mock_app_actions, fixture_library_data
    ):
        """A result matching playlist_track_exclusions must not be startable from
        search -- Playlist would silently drop it as a start track and crash
        (see set_start_track's "Playlist start track not in playlist!")."""
        from ui_qt.search_window import SearchWindow
        from muse.playlist import TRACK_EXCLUSIONS_KEY
        from utils.app_info_cache import app_info_cache

        app_info_cache.set(TRACK_EXCLUSIONS_KEY, ["Beethoven"])
        win = SearchWindow(qt_master, mock_app_actions, fixture_library_data)
        # Drain the __init__-scheduled QTimer.singleShot(0, show_recent_searches)
        # now, while there's nothing recent yet, so it can't fire later (mid
        # run_search_sync's own event-pump) and clobber the results grid we're
        # about to build with a stale "recent searches" view.
        process_events_for(0.1)
        win.composer_entry.setText("beethoven")
        win.library_data_search = LibraryDataSearch(composer="beethoven", max_results=20)
        count = run_search_sync(win)
        assert count > 0
        assert len(win.play_btn_list) == count
        for play_btn in win.play_btn_list:
            assert not play_btn.isEnabled()
            assert "Beethoven" in play_btn.toolTip()
        win.close()

    def test_non_excluded_result_play_button_stays_enabled(
        self, qapp, qt_master, mock_app_actions, fixture_library_data
    ):
        from ui_qt.search_window import SearchWindow
        from muse.playlist import TRACK_EXCLUSIONS_KEY
        from utils.app_info_cache import app_info_cache

        app_info_cache.set(TRACK_EXCLUSIONS_KEY, ["Beethoven"])
        win = SearchWindow(qt_master, mock_app_actions, fixture_library_data)
        process_events_for(0.1)  # drain the deferred show_recent_searches() timer first
        win.composer_entry.setText("mozart")
        win.library_data_search = LibraryDataSearch(composer="mozart", max_results=20)
        count = run_search_sync(win)
        assert count > 0
        assert len(win.play_btn_list) == count
        for play_btn in win.play_btn_list:
            assert play_btn.isEnabled()
            assert play_btn.toolTip() == ""
        win.close()


@pytest.mark.ui
class TestSearchResultDetailsButton:
    """The per-row Details button must reach the track details window.

    It was wired to a stub that silently did nothing, so clicking it appeared
    to work while opening no window.
    """

    def _open_with_results(self, qt_master, mock_app_actions, fixture_library_data):
        from ui_qt.search_window import SearchWindow

        win = SearchWindow(qt_master, mock_app_actions, fixture_library_data)
        # Drain the __init__-scheduled QTimer.singleShot(0, show_recent_searches)
        # before searching: it calls clear_widget_lists(), so firing later (inside
        # run_search_sync's own event pump) would discard the result rows.
        process_events_for(0.1)
        win.library_data_search = LibraryDataSearch(composer="beethoven", max_results=50)
        count = run_search_sync(win)
        assert count > 0, "fixture search returned no results"
        return win

    @staticmethod
    def _details_buttons(win):
        """The per-result Details buttons only.

        open_details_btn_list also holds the Search buttons of the recent-search
        rows, which are appended first, so indexing into it picks the wrong one.
        """
        from utils.translations import I18N

        return [b for b in win.open_details_btn_list if b.text() == I18N._("Details")]

    def test_details_button_opens_track_details_for_that_row(
        self, qapp, qt_master, mock_app_actions, fixture_library_data
    ):
        opened = []
        mock_app_actions._actions["open_track_details"] = lambda track: opened.append(track)

        win = self._open_with_results(qt_master, mock_app_actions, fixture_library_data)
        buttons = self._details_buttons(win)
        # One per result row; a mismatch means the recent-searches view replaced
        # the result grid rather than the Details wiring being wrong.
        assert len(buttons) == len(win.library_data_search.get_results())

        # click() rather than QTest.mouseClick: the result rows live in a scroll
        # area, so the button may have no clickable position on screen.
        buttons[0].click()
        process_events_for(0.2)

        assert len(opened) == 1
        assert opened[0] in win.library_data_search.get_results()
        win.close()

    def test_open_details_passes_the_track_through(
        self, qapp, qt_master, mock_app_actions, fixture_library_data
    ):
        opened = []
        mock_app_actions._actions["open_track_details"] = lambda track: opened.append(track)

        win = self._open_with_results(qt_master, mock_app_actions, fixture_library_data)
        track = win.library_data_search.get_results()[0]

        win.open_details(track)

        assert opened == [track]
        win.close()
