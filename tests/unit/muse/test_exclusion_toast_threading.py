"""
Regression tests: Playback.get_track() calls ui_callbacks.toast() from a
background thread, so the toast implementation must NOT touch Qt objects
directly — it must use a signal bridge (emit → slot on main thread).

Without the signal bridge the original implementation created a QMessageBox
directly from the playback thread, producing:
    QObject::setParent: Cannot set parent, new parent is in a different thread

These tests document the threading contract and would have caught that bug.
"""
import threading
import pytest
from unittest.mock import MagicMock

from utils.globals import TrackResult


@pytest.fixture(autouse=True)
def mock_vlc(monkeypatch):
    import muse.playback as playback_mod
    mock_inst = MagicMock()
    mock_inst.media_player_new.return_value = MagicMock()
    monkeypatch.setattr(playback_mod, "INSTANCE", mock_inst)


def _make_playback(ui_callbacks, mock_data_callbacks, excluded_count=3):
    from muse.playback import Playback
    from muse.playback_config import PlaybackConfig
    pc = PlaybackConfig(data_callbacks=mock_data_callbacks, explicit_tracks=[])
    p = Playback(playback_config=pc, ui_callbacks=ui_callbacks, run=None)
    mock_config = MagicMock()
    mock_config.next_track.return_value = TrackResult()
    mock_config.enable_long_track_splitting = False
    mock_config.get_list.return_value.excluded_count = excluded_count
    p._playback_config = mock_config
    return p


@pytest.mark.unit
class TestToastCalledFromBackgroundThread:
    def test_toast_is_invoked_from_non_main_thread(self, mock_data_callbacks):
        """
        When get_track() runs on the playback worker thread, the toast callback
        is invoked from that same non-main thread.  Any implementation that
        creates Qt widgets directly at call-time (without emitting a signal)
        will violate Qt's thread affinity rules.
        """
        called_from = []

        def recording_toast(message):
            called_from.append(threading.current_thread())

        ui = MagicMock()
        ui.toast = recording_toast
        p = _make_playback(ui, mock_data_callbacks, excluded_count=5)

        t = threading.Thread(target=p.get_track, name="playback-worker")
        t.start()
        t.join(timeout=5.0)

        assert len(called_from) == 1, "toast was not called"
        assert called_from[0] is not threading.main_thread(), (
            "toast was called on the main thread — if this changes, verify that "
            "the signal bridge in MuseAppQt.toast() is still necessary"
        )

    def test_no_toast_on_background_thread_when_count_is_zero(self, mock_data_callbacks):
        """toast must not be called at all when excluded_count is zero."""
        called_from = []

        def recording_toast(message):
            called_from.append(threading.current_thread())

        ui = MagicMock()
        ui.toast = recording_toast
        p = _make_playback(ui, mock_data_callbacks, excluded_count=0)

        t = threading.Thread(target=p.get_track, name="playback-worker")
        t.start()
        t.join(timeout=5.0)

        assert len(called_from) == 0

    def test_no_exception_raised_from_background_thread(self, mock_data_callbacks):
        """get_track() on a background thread must not raise."""
        errors = []

        def recording_toast(message):
            pass

        ui = MagicMock()
        ui.toast = recording_toast

        def worker():
            try:
                p = _make_playback(ui, mock_data_callbacks, excluded_count=3)
                p.get_track()
            except Exception as exc:
                errors.append(exc)

        t = threading.Thread(target=worker, name="playback-worker")
        t.start()
        t.join(timeout=5.0)

        assert not errors, f"get_track() raised from background thread: {errors}"
