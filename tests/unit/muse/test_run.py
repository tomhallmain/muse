"""
Unit tests for Run.run() in muse/run.py.

Covers the end-of-playback cleanup (FFmpeg cache and temp dir) on every way
Playback.run() can end: normally, on a scheduled shutdown, on an error, and on
KeyboardInterrupt. Each path cleans up exactly once. On a scheduled shutdown
cleanup comes before shutdown_callback, which can end the process.

Muse and LibraryData are mocked out; Playback is a MagicMock set on the Run.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from muse.playback_state import PlaybackStateManager
from muse.schedules_manager import ScheduledShutdownException


def _make_run(app_actions=None):
    from muse.run import Run
    from muse.run_config import RunConfig
    with patch("muse.run.Muse", return_value=MagicMock()), \
         patch("muse.run.LibraryData", return_value=MagicMock()):
        run = Run(RunConfig(placeholder=True), app_actions)
    run.library_data = MagicMock()
    run._playback = MagicMock()
    run._playback._playback_config = {"config": "played"}
    return run


@pytest.fixture
def calls():
    """One parent mock, so the order of cleanup and callback calls is recorded."""
    parent = MagicMock()
    with patch("muse.run.FFmpegHandler", parent.ffmpeg), \
         patch("muse.run.TempDir", parent.temp_dir), \
         patch("muse.run.config", SimpleNamespace(enable_library_extender=False)):
        yield parent


def _call_names(parent):
    return [c[0] for c in parent.mock_calls]


def _assert_cleaned_up_once(parent):
    parent.ffmpeg.cleanup_cache.assert_called_once_with()
    parent.temp_dir.cleanup.assert_called_once_with()


@pytest.mark.unit
class TestRunCleanup:

    def test_normal_end_cleans_up_once(self, calls):
        run = _make_run()
        run.run(MagicMock())
        run._playback.run.assert_called_once_with()
        _assert_cleaned_up_once(calls)

    def test_normal_end_records_last_config_copy(self, calls):
        run = _make_run()
        run.run(MagicMock())
        assert run.is_started
        assert run.last_config == {"config": "played"}
        assert run.last_config is not run._playback._playback_config

    def test_scheduled_shutdown_cleans_up_before_shutdown_callback(self, calls):
        run = _make_run(app_actions=calls.app_actions)
        run._playback.run.side_effect = ScheduledShutdownException("bedtime")
        run.run(MagicMock())
        _assert_cleaned_up_once(calls)
        calls.app_actions.shutdown_callback.assert_called_once_with()
        names = _call_names(calls)
        shutdown_at = names.index("app_actions.shutdown_callback")
        assert names.index("ffmpeg.cleanup_cache") < shutdown_at
        assert names.index("temp_dir.cleanup") < shutdown_at

    def test_scheduled_shutdown_without_app_actions_cleans_up_and_returns(self, calls):
        run = _make_run()
        run._playback.run.side_effect = ScheduledShutdownException("bedtime")
        run.run(MagicMock())  # must not raise
        _assert_cleaned_up_once(calls)

    def test_error_cleans_up_resets_extension_and_reraises(self, calls):
        run = _make_run()
        run._playback.run.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError, match="boom"):
            run.run(MagicMock())
        _assert_cleaned_up_once(calls)
        run.library_data.reset_extension.assert_called_once_with()

    def test_keyboard_interrupt_cleans_up_and_propagates(self, calls):
        # KeyboardInterrupt is not an Exception subclass; do_workflow catches it
        # above run(), so run() must still clean up on the way out.
        run = _make_run()
        run._playback.run.side_effect = KeyboardInterrupt()
        with pytest.raises(KeyboardInterrupt):
            run.run(MagicMock())
        _assert_cleaned_up_once(calls)

    @pytest.mark.parametrize("error", [
        None, ScheduledShutdownException("bedtime"), RuntimeError("boom"), KeyboardInterrupt(),
    ])
    def test_active_config_cleared_on_every_path(self, calls, error):
        run = _make_run()
        run._playback.run.side_effect = error
        try:
            run.run(MagicMock())
        except BaseException:
            pass
        assert PlaybackStateManager.get_active_config() is None

    def test_config_matching_last_config_does_not_play_or_clean_up(self, calls):
        run = _make_run()
        same = {"config": "played"}
        run.last_config = same
        run.run(same)
        run._playback.run.assert_not_called()
        calls.ffmpeg.cleanup_cache.assert_not_called()
        calls.temp_dir.cleanup.assert_not_called()
