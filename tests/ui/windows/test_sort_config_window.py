"""Sort configuration dialog tests."""

import pytest
from PySide6.QtWidgets import QDialog

from muse.sort_config import SortConfig
from tests.utils.qt_test_helpers import process_events_for


@pytest.mark.ui
class TestSortConfigWindow:
    def test_dialog_returns_updated_sort_config(self, qapp, qt_master):
        from ui_qt.sort_config_window import SortConfigWindow

        source = SortConfig(skip_memory_shuffle=False, skip_random_start=False)
        dlg = SortConfigWindow(parent=qt_master, sort_config=source)
        dlg._skip_memory_check.setChecked(True)
        dlg._skip_random_start_check.setChecked(True)
        dlg._check_entire_check.setChecked(True)
        dlg._cc_enabled_check.setChecked(True)
        dlg._cc_spin.setValue(42)
        dlg._on_accept()
        process_events_for(0.1)

        assert dlg.result() == QDialog.DialogCode.Accepted
        result = dlg.get_result()
        assert result is not None
        assert result.skip_memory_shuffle is True
        assert result.skip_random_start is True
        assert result.check_entire_playlist is True
        assert result.check_count_override == 42

    def test_cancel_leaves_no_result(self, qapp, qt_master):
        from ui_qt.sort_config_window import SortConfigWindow

        dlg = SortConfigWindow(parent=qt_master, sort_config=SortConfig())
        dlg.reject()
        assert dlg.get_result() is None

    def test_override_mode_shows_hint(self, qapp, qt_master):
        from ui_qt.sort_config_window import SortConfigWindow

        dlg = SortConfigWindow(parent=qt_master, is_override=True)
        assert dlg.windowTitle()
        dlg.close()
