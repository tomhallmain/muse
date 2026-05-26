"""Cross-window flow: search results align with playlist live preview (no VLC)."""

import pytest

from library_data.library_data import LibraryDataSearch
from tests.utils.playlist_assertions import build_expected_queue, verify_queue_order
from tests.utils.qt_test_helpers import find_highlighted, process_events_for, read_preview_items
from tests.utils.ui_window_helpers import (
    build_fixture_playback_master,
    run_search_sync,
)


@pytest.mark.ui
class TestSearchAndPreviewFlow:
    def test_search_order_matches_live_preview_queue(
        self,
        qapp,
        qt_master,
        mock_app_actions,
        fixture_library_data,
        audio_library_callbacks,
    ):
        from ui_qt.playlist_window import MasterPlaylistWindow
        from ui_qt.search_window import SearchWindow

        search_win = SearchWindow(qt_master, mock_app_actions, fixture_library_data)
        search_win.composer_entry.setText("beethoven")
        search_win.library_data_search = LibraryDataSearch(composer="beethoven", max_results=20)
        count = run_search_sync(search_win)
        assert count >= 5

        results = search_win.library_data_search.get_results()[:10]
        filepaths = [t.filepath for t in results]
        from muse.playback_config import PlaybackConfig
        from muse.playlist import Playlist
        from muse.sort_config import SortConfig

        playlist = Playlist(
            tracks=filepaths,
            data_callbacks=audio_library_callbacks,
            sort_config=SortConfig(skip_memory_shuffle=True, skip_random_start=True),
        )
        pc = PlaybackConfig(data_callbacks=audio_library_callbacks)
        pc.list = playlist

        from muse.playback_config_master import PlaybackConfigMaster
        from muse.playback_state import PlaybackStateManager

        master = PlaybackConfigMaster([pc])
        master.next_track()
        PlaybackStateManager.set_active_config(master)

        expected_titles = build_expected_queue(
            playlist,
            format_fn=MasterPlaylistWindow._format_track,
        )

        playlist_win = MasterPlaylistWindow(qt_master, mock_app_actions, fixture_library_data)
        playlist_win._update_live_preview(master)
        process_events_for(0.3)

        items = read_preview_items(playlist_win)
        assert find_highlighted(items) >= 0
        assert verify_queue_order(
            items,
            expected_titles,
            queue_start_row=playlist_win._queue_start_row,
            compare_limit=min(8, len(expected_titles)),
        )

        search_win.close()
        playlist_win.close()
