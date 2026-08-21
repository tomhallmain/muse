"""Tests for ui_qt/extensions_window.py (ExtensionsWindow / RejectedExtensionsWindow).

ExtensionManager's rejection state is class-level, so it's reset per test
below. Its app_info_cache is isolated via tests/conftest.py.
"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from extensions.extension_manager import ExtensionManager
from tests.utils.qt_test_helpers import process_events_for
from utils.translations import I18N

_ = I18N._


@pytest.fixture(autouse=True)
def _reset_extension_manager_state():
    ExtensionManager.extensions = []
    ExtensionManager.rejected_extensions = []
    ExtensionManager.rejected_ids = set()
    ExtensionManager.pending_candidate = None
    yield
    ExtensionManager.extensions = []
    ExtensionManager.rejected_extensions = []
    ExtensionManager.rejected_ids = set()
    ExtensionManager.pending_candidate = None


def _seed_rejection(id_="rej-1", title="Rejected Title"):
    ExtensionManager.rejected_extensions = [{
        "id": id_,
        "snippet": {"title": title},
        "date": "2024-01-01T00:00:00",
        "track_attr": "ARTIST",
        "search_query": "some query",
    }]
    ExtensionManager._recompute_rejected_ids()


def _seed_extension(id_="ext-1", title="Extension Title", filename=""):
    from extensions.library_extender import q20, q23, q27, q28

    ExtensionManager.extensions = [{
        q20: {q27: q28, q23: id_},
        "snippet": {"title": title},
        "filename": filename,
        "date": "2024-01-01T00:00:00",
        "track_attr": "ARTIST",
        "search_query": "some query",
        "failed": False,
    }]


@pytest.mark.ui
class TestExtensionsWindow:
    def test_opens(self, qapp, qt_master, mock_app_actions, fixture_library_data):
        from ui_qt.extensions_window import ExtensionsWindow

        win = ExtensionsWindow(qt_master, mock_app_actions, fixture_library_data)
        process_events_for(0.2)
        assert win.isVisible()
        win.close()

    def test_rejected_count_label_reflects_seeded_rejections(
        self, qapp, qt_master, mock_app_actions, fixture_library_data
    ):
        from ui_qt.extensions_window import ExtensionsWindow

        _seed_rejection()
        win = ExtensionsWindow(qt_master, mock_app_actions, fixture_library_data)
        process_events_for(0.2)
        assert win.rejected_count_label.text() == _("Rejected: {0}").format(1)
        win.close()

    def test_view_rejected_button_opens_rejected_window(
        self, qapp, qt_master, mock_app_actions, fixture_library_data
    ):
        from ui_qt.extensions_window import ExtensionsWindow

        win = ExtensionsWindow(qt_master, mock_app_actions, fixture_library_data)
        process_events_for(0.2)

        QTest.mouseClick(win.view_rejected_btn, Qt.MouseButton.LeftButton)
        process_events_for(0.2)

        opened = [
            w for w in qapp.topLevelWidgets()
            if w.isVisible() and w.windowTitle() == _("Rejected Extensions")
        ]
        assert len(opened) == 1
        opened[0].close()
        win.close()

    def test_delete_extension_also_rejects_it(
        self, qapp, qt_master, mock_app_actions, fixture_library_data
    ):
        from ui_qt.extensions_window import ExtensionsWindow

        _seed_extension(id_="ext-to-delete")
        win = ExtensionsWindow(qt_master, mock_app_actions, fixture_library_data)
        process_events_for(0.2)
        win.app_actions.alert = lambda *args, **kwargs: True

        QTest.mouseClick(win.delete_buttons[0], Qt.MouseButton.LeftButton)
        process_events_for(0.2)

        assert ExtensionManager.extensions == []
        assert len(ExtensionManager.rejected_extensions) == 1
        assert "ext-to-delete" in ExtensionManager.rejected_ids
        win.close()

    def test_declining_delete_confirmation_keeps_extension_unrejected(
        self, qapp, qt_master, mock_app_actions, fixture_library_data
    ):
        from ui_qt.extensions_window import ExtensionsWindow

        _seed_extension(id_="ext-to-keep")
        win = ExtensionsWindow(qt_master, mock_app_actions, fixture_library_data)
        process_events_for(0.2)
        win.app_actions.alert = lambda *args, **kwargs: False

        QTest.mouseClick(win.delete_buttons[0], Qt.MouseButton.LeftButton)
        process_events_for(0.2)

        assert len(ExtensionManager.extensions) == 1
        assert ExtensionManager.rejected_extensions == []
        assert "ext-to-keep" not in ExtensionManager.rejected_ids
        win.close()


@pytest.mark.ui
class TestRejectedExtensionsWindow:
    def test_empty_state(self, qapp, qt_master, mock_app_actions):
        from ui_qt.extensions_window import RejectedExtensionsWindow

        win = RejectedExtensionsWindow(qt_master, mock_app_actions)
        process_events_for(0.2)
        assert win.isVisible()
        assert len(win.title_labels) == 1
        assert win.title_labels[0].text() == _("No rejected extensions.")
        win.close()

    def test_seeded_rejection_is_listed(self, qapp, qt_master, mock_app_actions):
        from ui_qt.extensions_window import RejectedExtensionsWindow

        _seed_rejection(title="My Rejected Track")
        win = RejectedExtensionsWindow(qt_master, mock_app_actions)
        process_events_for(0.2)

        assert len(win.title_labels) == 1
        assert win.title_labels[0].text() == "My Rejected Track"
        assert win.attribute_labels[0].text() == "ARTIST"
        assert win.query_labels[0].text() == "some query"
        assert len(win.delete_buttons) == 1
        win.close()

    def test_delete_removes_rejection_and_updates_list(
        self, qapp, qt_master, mock_app_actions
    ):
        from ui_qt.extensions_window import RejectedExtensionsWindow

        _seed_rejection(id_="rej-to-delete")
        win = RejectedExtensionsWindow(qt_master, mock_app_actions)
        process_events_for(0.2)
        win.app_actions.alert = lambda *args, **kwargs: True

        QTest.mouseClick(win.delete_buttons[0], Qt.MouseButton.LeftButton)
        process_events_for(0.2)

        assert ExtensionManager.rejected_extensions == []
        assert "rej-to-delete" not in ExtensionManager.rejected_ids
        assert win.title_labels[0].text() == _("No rejected extensions.")
        win.close()

    def test_declining_confirmation_keeps_rejection(
        self, qapp, qt_master, mock_app_actions
    ):
        from ui_qt.extensions_window import RejectedExtensionsWindow

        _seed_rejection(id_="rej-keep")
        win = RejectedExtensionsWindow(qt_master, mock_app_actions)
        process_events_for(0.2)
        win.app_actions.alert = lambda *args, **kwargs: False

        QTest.mouseClick(win.delete_buttons[0], Qt.MouseButton.LeftButton)
        process_events_for(0.2)

        assert len(ExtensionManager.rejected_extensions) == 1
        assert "rej-keep" in ExtensionManager.rejected_ids
        win.close()
