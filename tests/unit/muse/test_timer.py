"""Unit tests for muse/timer.py.

Timer is a singleton that manages a countdown and optional playback volume
reduction.  All threading is either mocked out or driven by direct method calls
to keep tests fast and deterministic.

Isolation: `reset_timer_singleton` (autouse) tears down and recreates the
singleton around every test.  Timer does not touch app_info_cache, config, or
the DB, so no extra singleton patching is required beyond what the root conftest
already provides.
"""

from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_timer_singleton():
    """Destroy and recreate the Timer singleton around each test."""
    import muse.timer as timer_mod
    timer_mod.Timer._instance = None
    yield
    if timer_mod.Timer._instance is not None:
        try:
            timer_mod.Timer._instance.cleanup()
        except Exception:
            pass
    timer_mod.Timer._instance = None


@pytest.fixture
def timer():
    from muse.timer import Timer
    return Timer()


@pytest.fixture
def mock_playback():
    pb = MagicMock()
    pb.set_timer_volume_override = MagicMock()
    return pb


@pytest.fixture
def mock_threading(monkeypatch):
    """Replace muse.timer's reference to threading so Thread() returns a mock.

    Patching the module-level name rather than threading.Thread itself avoids
    polluting the real threading module for other code running in the same
    process.

    Pytest does not guarantee that `timer` is set up before this fixture when
    both appear as parameters on the same test.  The fixture handles both
    orderings: if `timer` ran first, its Event/Lock objects are already real;
    if this fixture runs first, `fake.Event.side_effect` and
    `fake.Lock.side_effect` delegate to the real constructors so that
    Timer.__init__ still gets real synchronisation primitives.  Either way,
    only Thread() calls (in start_timer / _start_beeping) return the mock.
    """
    import muse.timer as timer_mod
    import threading as real_threading

    fake = MagicMock(spec=real_threading)
    mock_thread = MagicMock()
    mock_thread.is_alive.return_value = False
    fake.Thread.return_value = mock_thread
    # Delegate Event/Lock construction to real implementations so __init__
    # synchronisation objects remain functional regardless of setup order.
    fake.Event.side_effect = real_threading.Event
    fake.Lock.side_effect = real_threading.Lock
    monkeypatch.setattr(timer_mod, "threading", fake)
    return fake, mock_thread


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTimerSingleton:
    def test_two_calls_return_same_instance(self):
        from muse.timer import Timer
        assert Timer() is Timer()

    def test_init_runs_only_once(self):
        from muse.timer import Timer
        t = Timer()
        t._sentinel = True
        assert hasattr(Timer(), "_sentinel")


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTimerInitialState:
    def test_status_is_stopped(self, timer):
        assert timer.get_status() == "stopped"

    def test_not_running(self, timer):
        assert not timer.is_running()

    def test_not_paused(self, timer):
        assert not timer.is_paused()

    def test_not_completed(self, timer):
        assert not timer.is_completed()

    def test_progress_is_zero_when_duration_unset(self, timer):
        assert timer.get_progress() == 0.0

    def test_remaining_time_is_zero(self, timer):
        assert timer.get_remaining_time() == 0


# ---------------------------------------------------------------------------
# start_timer / stop_timer
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTimerStartStop:
    def test_start_sets_running_state(self, timer, mock_threading):
        _, mock_thread = mock_threading
        timer.start_timer(60)
        assert timer.is_running()
        assert timer.get_status() == "running"
        assert timer._duration_seconds == 60
        assert timer._remaining_seconds == 60
        mock_thread.start.assert_called_once()

    def test_start_when_already_running_is_noop(self, timer, mock_threading):
        _, mock_thread = mock_threading
        timer.start_timer(60)
        timer.start_timer(30)               # second call must be ignored
        assert timer._duration_seconds == 60
        assert mock_thread.start.call_count == 1

    def test_stop_clears_running_flag(self, timer):
        timer._is_running = True
        timer.stop_timer()
        assert not timer.is_running()

    def test_stop_when_not_started_is_noop(self, timer):
        timer.stop_timer()                  # must not raise
        assert not timer.is_running()

    def test_stop_when_completed_is_allowed(self, timer):
        timer._is_completed = True
        timer.stop_timer()                  # must not raise

    def test_stop_restores_volume_if_reduced(self, timer, mock_playback):
        timer.set_playback_instance(mock_playback)
        timer._is_running = True
        timer._volume_reduced = True
        timer.stop_timer()
        mock_playback.set_timer_volume_override.assert_called_with(False, None)


# ---------------------------------------------------------------------------
# pause / resume
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTimerPauseResume:
    def test_pause_sets_paused_state(self, timer):
        timer._is_running = True
        timer.pause_timer()
        assert timer.is_paused()
        assert timer.get_status() == "paused"

    def test_pause_noop_when_not_running(self, timer):
        timer.pause_timer()
        assert not timer.is_paused()

    def test_resume_clears_paused_state(self, timer):
        timer._is_running = True
        timer._is_paused = True
        timer.resume_timer()
        assert not timer.is_paused()
        assert timer.get_status() == "running"

    def test_resume_noop_when_not_running(self, timer):
        timer._is_paused = True
        timer.resume_timer()
        assert timer._is_paused   # unchanged


# ---------------------------------------------------------------------------
# Progress and remaining time
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTimerProgress:
    def test_progress_at_start(self, timer):
        timer._duration_seconds = 60
        timer._remaining_seconds = 60
        assert timer.get_progress() == 0.0

    def test_progress_halfway(self, timer):
        timer._duration_seconds = 60
        timer._remaining_seconds = 30
        assert timer.get_progress() == pytest.approx(0.5)

    def test_progress_clamped_at_one(self, timer):
        timer._duration_seconds = 60
        timer._remaining_seconds = -10
        assert timer.get_progress() == 1.0

    def test_remaining_time_positive(self, timer):
        timer._remaining_seconds = 45
        assert timer.get_remaining_time() == 45

    def test_remaining_time_clamped_at_zero(self, timer):
        timer._remaining_seconds = -5
        assert timer.get_remaining_time() == 0


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTimerExpiry:
    def test_expired_marks_completed(self, timer, monkeypatch):
        monkeypatch.setattr(timer, "_start_beeping", MagicMock())
        timer._timer_expired()
        assert timer.is_completed()
        assert not timer.is_running()
        assert timer.get_status() == "completed"

    def test_expired_reduces_volume(self, timer, mock_playback, monkeypatch):
        timer.set_playback_instance(mock_playback)
        monkeypatch.setattr(timer, "_start_beeping", MagicMock())
        timer._timer_expired()
        mock_playback.set_timer_volume_override.assert_called_once_with(
            True, timer._reduced_volume
        )
        assert timer._volume_reduced


# ---------------------------------------------------------------------------
# Volume control
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTimerVolumeControl:
    def test_reduce_volume_calls_playback(self, timer, mock_playback):
        timer.set_playback_instance(mock_playback)
        timer._reduce_volume()
        mock_playback.set_timer_volume_override.assert_called_once_with(
            True, timer._reduced_volume
        )
        assert timer._volume_reduced

    def test_reduce_volume_noop_without_playback(self, timer):
        timer._reduce_volume()              # must not raise
        assert not timer._volume_reduced

    def test_reduce_volume_noop_if_already_reduced(self, timer, mock_playback):
        timer.set_playback_instance(mock_playback)
        timer._volume_reduced = True
        timer._reduce_volume()
        mock_playback.set_timer_volume_override.assert_not_called()

    def test_restore_volume_calls_playback(self, timer, mock_playback):
        timer.set_playback_instance(mock_playback)
        timer._volume_reduced = True
        timer._restore_volume()
        mock_playback.set_timer_volume_override.assert_called_once_with(False, None)
        assert not timer._volume_reduced

    def test_restore_volume_noop_without_playback(self, timer):
        timer._volume_reduced = True
        timer._restore_volume()
        assert timer._volume_reduced        # unchanged

    def test_restore_volume_noop_if_not_reduced(self, timer, mock_playback):
        timer.set_playback_instance(mock_playback)
        timer._volume_reduced = False
        timer._restore_volume()
        mock_playback.set_timer_volume_override.assert_not_called()

    def test_set_playback_instance(self, timer, mock_playback):
        timer.set_playback_instance(mock_playback)
        assert timer._playback_instance is mock_playback


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTimerCleanup:
    def test_cleanup_stops_running_timer(self, timer):
        timer._is_running = True
        timer.cleanup()
        assert not timer.is_running()

    def test_cleanup_when_idle_does_not_raise(self, timer):
        timer.cleanup()
