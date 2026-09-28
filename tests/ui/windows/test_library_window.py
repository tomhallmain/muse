"""Library statistics window tests."""

import datetime
import time

import pytest
from PySide6.QtWidgets import QApplication

from tests.utils.qt_test_helpers import process_events_for
from utils.translations import I18N

_ = I18N._


def _wait_until_loaded(win, timeout: float = 15.0):
    deadline = time.time() + timeout
    while win._snapshot is None and time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.05)
    assert win._snapshot is not None, "library window data did not load"


def _rows(win):
    table = win.table
    return {
        table.item(r, 0).text(): tuple(table.item(r, c).text() for c in range(1, 4))
        for r in range(table.rowCount())
    }


@pytest.mark.ui
class TestLibraryWindow:
    def test_statistics_match_fixture_track_count(
        self, qapp, qt_master, mock_app_actions, fixture_library_data, audio_library_media_tracks
    ):
        from ui_qt.library_window import LibraryWindow

        win = LibraryWindow(qt_master, mock_app_actions, fixture_library_data)
        _wait_until_loaded(win)
        assert win.isVisible()

        total_text = win.total_tracks_label.text()
        assert str(len(audio_library_media_tracks)) in total_text
        assert win.total_albums_label.text()
        assert win.total_composers_label.text()
        win.close()

    def test_window_shows_before_the_data_and_fills_in_after(
        self, qapp, qt_master, mock_app_actions, fixture_library_data, monkeypatch
    ):
        import ui_qt.library_window as library_window_module
        from ui_qt.library_window import LibraryWindow

        started = []
        monkeypatch.setattr(library_window_module.Utils, "start_thread",
                            lambda fn, use_asyncio=True, args=None: started.append((fn, args)))

        win = LibraryWindow(qt_master, mock_app_actions, fixture_library_data)
        process_events_for(0.2)
        assert win.isVisible()
        assert win.loading_label.isVisible()
        assert not win.table.isVisible()
        assert not win.attribute_combo.isEnabled()

        fn, args = started[0]
        fn(*args)
        _wait_until_loaded(win)
        assert not win.loading_label.isVisible()
        assert win.table.isVisible()
        assert win.attribute_combo.isEnabled()
        win.close()

    def test_a_superseded_load_is_ignored(
        self, qapp, qt_master, mock_app_actions, fixture_library_data, monkeypatch
    ):
        import ui_qt.library_window as library_window_module
        from ui_qt.library_window import LibraryWindow

        started = []
        monkeypatch.setattr(library_window_module.Utils, "start_thread",
                            lambda fn, use_asyncio=True, args=None: started.append((fn, args)))
        win = LibraryWindow(qt_master, mock_app_actions, fixture_library_data)
        win.update()

        stale_fn, stale_args = started[0]
        stale_fn(*stale_args)
        process_events_for(0.2)
        assert win._snapshot is None

        fresh_fn, fresh_args = started[1]
        fresh_fn(*fresh_args)
        _wait_until_loaded(win)
        win.close()

    def test_plays_are_summed_per_group(
        self, qapp, qt_master, mock_app_actions, fixture_library_data, audio_library_media_tracks
    ):
        from library_data import play_counts
        from ui_qt.library_window import LibraryWindow
        from utils.globals import TrackAttribute

        tracks = [t for t in fixture_library_data.get_all_tracks() if t.album]
        album = tracks[0].album
        same_album = [t for t in tracks if t.album == album]
        play_counts.record_play(same_album[0], when=datetime.datetime(2026, 9, 1, 10, 0))
        play_counts.record_play(same_album[0], when=datetime.datetime(2026, 9, 2, 10, 0))
        play_counts.record_play(same_album[-1], when=datetime.datetime(2026, 9, 3, 10, 0))

        win = LibraryWindow(qt_master, mock_app_actions, fixture_library_data)
        _wait_until_loaded(win)
        win.attribute_combo.setCurrentText(TrackAttribute.ALBUM.get_translation())

        # With a one-track album all three plays land on the same track, so the
        # group totals are the same either way.
        assert _rows(win)[album] == (str(len(same_album)), "3", "2026-09-03")
        assert win.total_plays_label.text() == _("Total Plays: {}").format(3)
        win.close()
