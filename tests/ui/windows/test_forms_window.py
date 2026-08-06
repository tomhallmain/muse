"""Forms window tests (isolated metadata / DB)."""

import pytest
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt

from library_data.form import FormsDataSearch
from tests.utils.qt_test_helpers import process_events_for


@pytest.mark.ui
class TestFormsWindow:
    def test_opens(self, qapp, qt_master, mock_app_actions):
        from ui_qt.forms_window import FormsWindow

        win = FormsWindow(qt_master, mock_app_actions)
        process_events_for(0.3)
        assert win.isVisible()
        win.close()

    def test_search_sonata_in_seeded_forms(self, qapp, qt_master, mock_app_actions):
        from library_data.form import forms_data
        from ui_qt.forms_window import FormsWindow

        search = FormsDataSearch(form="sonata")
        forms_data.do_search(search)
        assert len(search.get_results()) > 0

        win = FormsWindow(qt_master, mock_app_actions)
        process_events_for(0.3)
        win.form_entry.setText("sonata")
        QTest.mouseClick(win.search_btn, Qt.MouseButton.LeftButton)
        process_events_for(0.5)
        assert win.form_data_search is not None
        assert len(win.form_data_search.get_results()) > 0
        win.close()

    def test_list_all_forms(self, qapp, qt_master, mock_app_actions):
        from ui_qt.forms_window import FormsWindow

        win = FormsWindow(qt_master, mock_app_actions)
        process_events_for(0.3)
        QTest.mouseClick(win.list_all_btn, Qt.MouseButton.LeftButton)
        process_events_for(0.5)
        assert win.form_data_search is not None
        assert len(win.form_data_search.get_results()) > 0
        win.close()

    def test_recent_form_searches_stored_in_app_info_cache(
        self, qapp, qt_master, mock_app_actions, isolated_singletons
    ):
        from library_data.form import forms_data
        from ui_qt.forms_window import FormsWindow
        from utils.app_info_cache import app_info_cache

        search = FormsDataSearch(form="sonata")
        forms_data.do_search(search)
        search.set_stored_results_count()
        FormsWindow.recent_searches = [search]
        FormsWindow.store_recent_searches()
        app_info_cache.store()

        FormsWindow.recent_searches = []
        FormsWindow.load_recent_searches()
        assert len(FormsWindow.recent_searches) >= 1
        assert FormsWindow.recent_searches[0].form == "sonata"
