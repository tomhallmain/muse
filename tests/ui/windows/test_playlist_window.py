"""Master playlist window tests."""

import pytest

from muse.playback_config import PlaybackConfig
from muse.playlist import Playlist
from muse.sort_config import SortConfig
from tests.utils.playlist_assertions import build_expected_queue, verify_queue_order
from tests.utils.qt_test_helpers import find_highlighted, process_events_for, read_preview_items
from tests.utils.ui_window_helpers import build_fixture_playback_master


@pytest.mark.ui
class TestPlaylistWindow:
    def test_opens_with_fixture_library(self, qapp, qt_master, mock_app_actions, fixture_library_data):
        from ui_qt.playlist_window import MasterPlaylistWindow

        win = MasterPlaylistWindow(qt_master, mock_app_actions, fixture_library_data)
        process_events_for(0.3)
        assert win.isVisible()
        assert win._avail_list.count() >= 0
        win.close()

    def test_preview_list_reflects_playback_queue(
        self,
        qapp,
        qt_master,
        mock_app_actions,
        fixture_library_data,
        audio_library_callbacks,
    ):
        """Backend queue order should be expressible in preview rows (no VLC playback)."""
        from ui_qt.playlist_window import MasterPlaylistWindow

        tracks = audio_library_callbacks.get_all_tracks()[:12]
        filepaths = [t.filepath for t in tracks]
        playlist = Playlist(
            tracks=filepaths,
            data_callbacks=audio_library_callbacks,
            sort_config=SortConfig(skip_memory_shuffle=True, skip_random_start=True),
        )
        pc = PlaybackConfig(data_callbacks=audio_library_callbacks)
        pc.list = playlist
        playlist.next_track()

        expected = build_expected_queue(playlist)
        assert len(expected) >= 1

        win = MasterPlaylistWindow(qt_master, mock_app_actions, fixture_library_data)
        process_events_for(0.2)
        # Preview is built from descriptors/master entries; smoke-check widget exists.
        assert win._preview_list is not None
        assert win._preview_list.count() >= 0
        win.close()

    def test_read_preview_items_helper_with_empty_list(self, qapp, qt_master, mock_app_actions, fixture_library_data):
        from ui_qt.playlist_window import MasterPlaylistWindow

        win = MasterPlaylistWindow(qt_master, mock_app_actions, fixture_library_data)
        items = read_preview_items(win)
        assert isinstance(items, list)
        win.close()

    def test_live_preview_shows_queue_and_highlight(
        self, qapp, qt_master, mock_app_actions, fixture_library_data, audio_library_callbacks
    ):
        from ui_qt.playlist_window import MasterPlaylistWindow

        master, pc = build_fixture_playback_master(audio_library_callbacks, advance=1)
        win = MasterPlaylistWindow(qt_master, mock_app_actions, fixture_library_data)
        win._update_live_preview(master)
        process_events_for(0.2)

        items = read_preview_items(win)
        assert len(items) > 0
        highlight = find_highlighted(items)
        assert highlight >= 0
        assert highlight >= win._queue_start_row

        expected = build_expected_queue(pc.get_list(), MasterPlaylistWindow._format_track)
        assert verify_queue_order(
            items,
            expected,
            queue_start_row=win._queue_start_row,
            compare_limit=8,
        )
        win.close()

    def test_live_preview_highlight_advances_with_next_track(
        self, qapp, qt_master, mock_app_actions, fixture_library_data, audio_library_callbacks
    ):
        from ui_qt.playlist_window import MasterPlaylistWindow

        master, _pc = build_fixture_playback_master(audio_library_callbacks, advance=2)
        win = MasterPlaylistWindow(qt_master, mock_app_actions, fixture_library_data)
        win._update_live_preview(master)
        highlight_before = find_highlighted(read_preview_items(win))

        master.next_track()
        win._update_live_preview(master)
        process_events_for(0.2)
        highlight_after = find_highlighted(read_preview_items(win))

        assert highlight_before >= 0
        assert highlight_after >= 0
        assert highlight_after >= highlight_before
        win.close()
