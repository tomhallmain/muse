"""Smoke tests for the main Qt application window."""

import os

import pytest

from tests.utils.qt_test_helpers import process_events_for


@pytest.mark.ui
class TestAppShell:
    def test_muse_app_qt_constructs_and_closes(self, qapp, isolated_singletons):
        """Boot ``MuseAppQt`` offscreen with isolated caches; no playback started."""
        from app_qt import MuseAppQt

        window = MuseAppQt()
        window.resize(800, 600)
        window.show()
        process_events_for(1.0)
        assert window.isVisible()

        cache_dir = os.environ.get("MUSE_CACHE_DIR", "")
        assert cache_dir
        assert cache_dir in str(
            __import__("utils.app_info_cache", fromlist=["app_info_cache"]).app_info_cache._cache_loc
        )

        window.close()
        process_events_for(0.5)
        qapp.processEvents()
