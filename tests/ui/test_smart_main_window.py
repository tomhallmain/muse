"""Tests for SmartMainWindow's non-maximized geometry tracking.

Bug: closeEvent saved self.geometry() unconditionally, so closing the app
while maximized persisted the screen-filling geometry as "the" window size --
the next launch restored a "normal" window sized like a maximized one, with
no way back to the size the listener actually preferred.
"""

from PySide6.QtCore import QRect

import pytest

from lib.multi_display_qt import SmartMainWindow
from lib.position_data_qt import PositionData
from utils.app_info_cache import app_info_cache


@pytest.fixture
def window(qapp):
    win = SmartMainWindow(restore_geometry=True)
    yield win
    win.close()
    qapp.processEvents()


@pytest.mark.ui
class TestTrackNormalGeometry:
    def test_tracks_geometry_when_not_maximized(self, window):
        window.setGeometry(QRect(10, 20, 800, 600))

        window._track_normal_geometry()

        assert window._normal_geometry == QRect(10, 20, 800, 600)

    def test_does_not_track_while_maximized(self, window, monkeypatch):
        window.setGeometry(QRect(10, 20, 800, 600))
        window._track_normal_geometry()
        monkeypatch.setattr(window, "isMaximized", lambda: True)

        window.setGeometry(QRect(0, 0, 1920, 1080))  # what the maximized state looks like
        window._track_normal_geometry()

        assert window._normal_geometry == QRect(10, 20, 800, 600)

    def test_does_not_track_while_minimized(self, window, monkeypatch):
        window.setGeometry(QRect(10, 20, 800, 600))
        window._track_normal_geometry()
        monkeypatch.setattr(window, "isMinimized", lambda: True)

        window.setGeometry(QRect(-32000, -32000, 800, 600))  # Windows' minimized geometry
        window._track_normal_geometry()

        assert window._normal_geometry == QRect(10, 20, 800, 600)

    def test_resumes_tracking_once_restored(self, window, monkeypatch):
        window.setGeometry(QRect(10, 20, 800, 600))
        window._track_normal_geometry()
        monkeypatch.setattr(window, "isMaximized", lambda: True)
        window._track_normal_geometry()

        monkeypatch.setattr(window, "isMaximized", lambda: False)
        window.setGeometry(QRect(50, 60, 900, 700))
        window._track_normal_geometry()

        assert window._normal_geometry == QRect(50, 60, 900, 700)


@pytest.mark.ui
class TestCloseEventSavesTheRightGeometry:
    def test_maximized_close_saves_the_tracked_normal_geometry(self, window, monkeypatch):
        from PySide6.QtGui import QCloseEvent

        window.setGeometry(QRect(10, 20, 800, 600))
        window._track_normal_geometry()
        monkeypatch.setattr(window, "isMaximized", lambda: True)
        window.setGeometry(QRect(0, 0, 1920, 1080))

        saved = {}
        monkeypatch.setattr(
            app_info_cache, "set_display_position",
            lambda master, geometry=None: saved.setdefault("geometry", geometry),
        )
        monkeypatch.setattr(app_info_cache, "set_virtual_screen_info", lambda master: None)
        monkeypatch.setattr(app_info_cache, "store", lambda: None)

        window.closeEvent(QCloseEvent())

        assert saved["geometry"] == QRect(10, 20, 800, 600)

    def test_normal_close_saves_no_override(self, window, monkeypatch):
        """Not maximized: the current geometry is already correct, so no
        override is needed -- PositionData.from_master falls back to it."""
        from PySide6.QtGui import QCloseEvent

        window.setGeometry(QRect(10, 20, 800, 600))
        window._track_normal_geometry()

        saved = {}
        monkeypatch.setattr(
            app_info_cache, "set_display_position",
            lambda master, geometry=None: saved.setdefault("geometry", geometry),
        )
        monkeypatch.setattr(app_info_cache, "set_virtual_screen_info", lambda master: None)
        monkeypatch.setattr(app_info_cache, "store", lambda: None)

        window.closeEvent(QCloseEvent())

        assert saved["geometry"] is None


@pytest.mark.ui
class TestPositionDataGeometryOverride:
    def test_explicit_geometry_is_used_over_the_window_s_current_one(self, window):
        window.setGeometry(QRect(0, 0, 1920, 1080))

        position = PositionData.from_master(window, geometry=QRect(10, 20, 800, 600))

        assert (position.x, position.y, position.width, position.height) == (10, 20, 800, 600)

    def test_no_override_falls_back_to_the_window_s_current_geometry(self, window):
        window.setGeometry(QRect(10, 20, 800, 600))

        position = PositionData.from_master(window)

        assert (position.x, position.y, position.width, position.height) == (10, 20, 800, 600)
