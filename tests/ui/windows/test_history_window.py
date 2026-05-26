"""History window tests."""

import pytest

from muse.playlist import Playlist
from tests.utils.qt_test_helpers import process_events_for


@pytest.mark.ui
class TestHistoryWindow:
    def test_opens(self, qapp, qt_master, mock_app_actions, fixture_library_data):
        from ui_qt.history_window import HistoryWindow

        win = HistoryWindow(qt_master, mock_app_actions, fixture_library_data)
        process_events_for(0.3)
        assert win.isVisible()
        win.close()

    def test_search_finds_recent_filepath_entry(
        self, qapp, qt_master, mock_app_actions, fixture_library_data, audio_library_media_tracks
    ):
        from ui_qt.history_window import HistoryWindow

        track = audio_library_media_tracks[0]
        Playlist.recently_played_filepaths = [track.filepath]
        Playlist.recently_played_albums = [track.album or ""]
        Playlist.recently_played_artists = [track.artist or ""]

        win = HistoryWindow(qt_master, mock_app_actions, fixture_library_data)
        term = (track.title or "symphony")[:8].lower()
        win.search_entry.setText(term)
        win.do_search()
        process_events_for(0.3)
        assert win.history_data_search is not None
        assert len(win.history_data_search.get_results()) > 0
        win.close()
