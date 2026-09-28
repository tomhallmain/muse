"""Track details window tests."""

import os

import pytest
from PySide6.QtWidgets import QLabel

from tests.utils.qt_test_helpers import process_events_for


@pytest.mark.ui
class TestTrackDetailsWindow:
    def test_displays_fixture_track_metadata(
        self, qapp, qt_master, mock_app_actions, audio_library_media_tracks
    ):
        from ui_qt.track_details_window import TrackDetailsWindow

        track = audio_library_media_tracks[0]
        win = TrackDetailsWindow(qt_master, mock_app_actions, track)
        process_events_for(0.3)

        assert win.isVisible()
        assert win.title_edit.text() == (track.title or "")
        assert win.composer_edit.text() == (track.composer or "")
        assert win.album_edit.text() == (track.album or "")
        assert win.artist_edit.text() == (track.artist or "")

        label_texts = " ".join(w.text() for w in win.findChildren(QLabel))
        assert os.path.basename(track.filepath) in label_texts
        assert track.get_track_length() > 0
        win.close()

    def test_reload_from_file_replaces_cached_values(
        self, qapp, qt_master, mock_app_actions, audio_library_media_tracks, monkeypatch
    ):
        import library_data.library_data as library_data_module
        from library_data.media_track import MediaTrack
        from ui_qt.track_details_window import TrackDetailsWindow

        monkeypatch.setattr(library_data_module, "reset_store", lambda: None)
        track = audio_library_media_tracks[0]
        from_file = MediaTrack(track.filepath).title
        track.title = "Stale Title"
        win = TrackDetailsWindow(qt_master, mock_app_actions, track)
        process_events_for(0.3)
        assert win.title_edit.text() == "Stale Title"

        win.reload_btn.click()

        assert track.title == from_file
        assert win.title_edit.text() == (from_file or "")
        win.close()
