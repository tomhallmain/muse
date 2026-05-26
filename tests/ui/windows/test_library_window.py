"""Library statistics window tests."""

import pytest

from tests.utils.qt_test_helpers import process_events_for


@pytest.mark.ui
class TestLibraryWindow:
    def test_statistics_match_fixture_track_count(
        self, qapp, qt_master, mock_app_actions, fixture_library_data, audio_library_media_tracks
    ):
        from ui_qt.library_window import LibraryWindow

        win = LibraryWindow(qt_master, mock_app_actions, fixture_library_data)
        process_events_for(0.3)
        assert win.isVisible()

        total_text = win.total_tracks_label.text()
        assert str(len(audio_library_media_tracks)) in total_text
        assert win.total_albums_label.text()
        assert win.total_composers_label.text()
        win.close()
