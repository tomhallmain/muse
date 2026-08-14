"""Instruments window tests (isolated metadata / DB)."""

import pytest
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt

from library_data.instrument import InstrumentsDataSearch
from tests.utils.qt_test_helpers import process_events_for


@pytest.mark.ui
class TestInstrumentsWindow:
    def test_opens(self, qapp, qt_master, mock_app_actions):
        from ui_qt.instruments_window import InstrumentsWindow

        win = InstrumentsWindow(qt_master, mock_app_actions)
        process_events_for(0.3)
        assert win.isVisible()
        win.close()

    def test_search_accordion_in_seeded_instruments(self, qapp, qt_master, mock_app_actions):
        from library_data.instrument import instruments_data
        from ui_qt.instruments_window import InstrumentsWindow

        search = InstrumentsDataSearch(instrument="accordion")
        instruments_data.do_search(search)
        assert len(search.get_results()) > 0

        win = InstrumentsWindow(qt_master, mock_app_actions)
        process_events_for(0.3)
        win.instrument_entry.setText("accordion")
        QTest.mouseClick(win.search_btn, Qt.MouseButton.LeftButton)
        process_events_for(0.5)
        assert win.instrument_data_search is not None
        assert len(win.instrument_data_search.get_results()) > 0
        win.close()

    def test_list_all_instruments(self, qapp, qt_master, mock_app_actions):
        from ui_qt.instruments_window import InstrumentsWindow

        win = InstrumentsWindow(qt_master, mock_app_actions)
        process_events_for(0.3)
        QTest.mouseClick(win.list_all_btn, Qt.MouseButton.LeftButton)
        process_events_for(0.5)
        assert win.instrument_data_search is not None
        assert len(win.instrument_data_search.get_results()) > 0
        win.close()

    def test_recent_instrument_searches_stored_in_app_info_cache(
        self, qapp, qt_master, mock_app_actions, isolated_singletons
    ):
        from library_data.instrument import instruments_data
        from ui_qt.instruments_window import InstrumentsWindow
        from utils.app_info_cache import app_info_cache

        search = InstrumentsDataSearch(instrument="accordion")
        instruments_data.do_search(search)
        search.set_stored_results_count()
        InstrumentsWindow.recent_searches = [search]
        InstrumentsWindow.store_recent_searches()
        app_info_cache.store()

        InstrumentsWindow.recent_searches = []
        InstrumentsWindow.load_recent_searches()
        assert len(InstrumentsWindow.recent_searches) >= 1
        assert InstrumentsWindow.recent_searches[0].instrument == "accordion"

    def test_close_persists_and_reopen_restores_recent_search(
        self, qapp, qt_master, mock_app_actions, isolated_singletons
    ):
        """InstrumentsWindow wires load/store into __init__/closeEvent, same as
        GenresWindow/ArtistsWindow — see docs/property-config-windows.md for
        why Forms/Composers don't do this despite defining both methods.
        """
        from ui_qt.instruments_window import InstrumentsWindow

        InstrumentsWindow.recent_searches = []

        win = InstrumentsWindow(qt_master, mock_app_actions)
        process_events_for(0.3)
        win.instrument_entry.setText("accordion")
        QTest.mouseClick(win.search_btn, Qt.MouseButton.LeftButton)
        process_events_for(0.5)
        win.close()
        process_events_for(0.1)

        InstrumentsWindow.recent_searches = []
        win2 = InstrumentsWindow(qt_master, mock_app_actions)
        process_events_for(0.3)
        assert any(s.instrument == "accordion" for s in InstrumentsWindow.recent_searches)
        win2.close()
