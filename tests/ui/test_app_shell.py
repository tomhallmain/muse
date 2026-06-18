"""Smoke tests for the main Qt application window."""

import os

import pytest

from tests.utils.qt_test_helpers import process_events_for, read_preview_items


@pytest.mark.ui
class TestAppShell:
    def test_get_current_track_safe_before_run_initializes(
        self,
        qapp,
        fixture_library_data,
        audio_library_media_tracks,
        monkeypatch,
    ):
        """``get_current_track`` must not raise before the Run's Playback is initialized.

        Sequence that triggered the regression: ``_run_impl`` calls
        ``_show_progress_widgets`` (→ ``_refresh_session_buttons`` →
        ``get_current_track``) synchronously on the main thread *before*
        ``Utils.start_thread`` hands off to the VLC worker.  At that moment
        ``current_run`` is still the placeholder Run (``_playback=None``,
        ``is_started=False``).

        We block only the background thread from starting so the test stays
        deterministic; everything up to that hand-off runs for real.
        """
        from app_qt import MuseAppQt
        from utils.utils import Utils

        monkeypatch.setattr(Utils, "start_thread", staticmethod(lambda *a, **kw: None))

        window = MuseAppQt()
        window.show()
        process_events_for(0.2)

        # Sanity: placeholder Run, no Playback assigned yet.
        assert not window.current_run.is_started
        assert window.current_run._playback is None

        # Press play with a real fixture track.
        window.start_playback(track=audio_library_media_tracks[0])

        # Let the debouncer fire _run_impl on the main thread (debounce = 0.4 s).
        process_events_for(0.6)

        # _run_impl called _show_progress_widgets → _refresh_session_buttons →
        # get_current_track while current_run was still the uninitialised
        # placeholder.  Both assertions below would have failed before the fix.
        assert window._run_controls_active, "_show_progress_widgets was not called"
        assert window.get_current_track() is None

        window.close()
        process_events_for(0.5)
        qapp.processEvents()

    def test_playlist_has_all_library_tracks_after_play(
        self,
        qapp,
        fixture_library_data,
        audio_library_media_tracks,
        monkeypatch,
    ):
        """After pressing Play the playlist window must show every library track.

        Regression: an inverted is_stream() condition in PlaybackConfig.get_list()
        caused local-media runs to build a single-track playlist.

        VLC's INSTANCE and Playback.run are the only stubs — no audio hardware
        needed and the VLC wait-loop doesn't block.  Everything else (buttons,
        combo, window opening, playlist rendering) drives itself.
        """
        import time as _time
        from unittest.mock import MagicMock
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        import muse.playback as playback_mod
        from app_qt import MuseAppQt
        from muse.playback import Playback
        from ui_qt.playlist_window import MasterPlaylistWindow
        from utils.globals import PlaybackMasterStrategy

        mock_vlc_inst = MagicMock()
        mock_vlc_inst.media_player_new.return_value = MagicMock()
        monkeypatch.setattr(playback_mod, "INSTANCE", mock_vlc_inst)
        monkeypatch.setattr(Playback, "run", lambda self: None)

        window = MuseAppQt()
        window.show()
        process_events_for(0.2)

        # Configure via the UI combo, then click Play.
        window.playlist_strategy_combo.setCurrentText(
            PlaybackMasterStrategy.ALL_MUSIC.get_translation()
        )
        QTest.mouseClick(window.run_btn, Qt.MouseButton.LeftButton)

        # Wait for the background thread to create the Run and complete
        # (Playback.run is a no-op so it finishes almost immediately).
        expected_count = len(audio_library_media_tracks)
        deadline = _time.time() + 5.0
        while _time.time() < deadline:
            process_events_for(0.2)
            run = window.current_run
            if run is not None and not run.is_placeholder() and run.is_complete:
                break

        run = window.current_run
        assert run is not None and not run.is_placeholder(), "Run never started"
        assert run.is_complete, "Run did not complete within timeout"

        # Core assertion: every library track must be in the playlist.
        pc = run._playback._playback_config.playback_configs[0]
        assert pc.get_list().size() == expected_count, (
            f"PlaybackConfig.get_list() returned {pc.get_list().size()} track(s); "
            f"expected {expected_count}. Likely cause: inverted is_stream() condition."
        )

        # Click the Playlists button — the real window opens via window.app_actions.
        QTest.mouseClick(window.playlists_btn, Qt.MouseButton.LeftButton)
        process_events_for(0.3)

        playlist_win = MasterPlaylistWindow.top_level
        assert playlist_win is not None, "Playlist window did not open"

        # PlaybackStateManager is cleared on run completion, so feed the master
        # directly — the same pattern used in the dedicated playlist window tests.
        master = run._playback._playback_config
        master.next_track()  # establish queue position so pending_tracks is non-empty
        playlist_win._update_live_preview(master)
        process_events_for(0.2)

        items = read_preview_items(playlist_win)
        assert len(items) > 0, "Playlist preview is empty"

        # Validate titles: every row shown must be a real fixture track, and
        # the first page of the sorted playlist must all appear in the preview.
        library_keys = {
            MasterPlaylistWindow._format_track(t) for t in audio_library_media_tracks
        }
        displayed_keys = [
            text.split(". ", 1)[1] for text, _ in items if ". " in text
        ]
        for key in displayed_keys:
            assert key in library_keys, (
                f"Playlist window shows unexpected track: '{key}'"
            )

        # The preview shows: current track (highlighted at row 0) + first 29 pending
        # tracks — i.e. sorted_tracks[:30] in total.
        playlist = pc.get_list()
        preview_keys = set(displayed_keys)
        for track in playlist.sorted_tracks[:30]:
            expected_key = MasterPlaylistWindow._format_track(track)
            assert expected_key in preview_keys, (
                f"Expected track '{expected_key}' missing from playlist window preview."
            )

        playlist_win.close()
        window.close()
        process_events_for(0.5)
        qapp.processEvents()

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
