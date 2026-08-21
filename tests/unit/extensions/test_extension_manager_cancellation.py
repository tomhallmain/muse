"""Cooperative cancellation of the extension threads.

Before stop_event existed, reset_extension set a `should_stop` attribute that
nothing read, and every loop slept through `time.sleep`. A stop therefore never
stopped anything: the join timed out, the thread reference was dropped, and the
next start spawned a second thread alongside the orphaned first one. These tests
cover the mechanism that replaced it.
"""

import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from extensions.extension_manager import ExtensionManager


@pytest.fixture(autouse=True)
def restore_class_state():
    """These tests mutate ExtensionManager class-level state; put it back.

    reset_extension also cancels the shared EXTENSION_QUEUE, so that is saved too.
    Everything starts from a known state rather than whatever the previous test
    left behind.
    """
    queue = ExtensionManager.EXTENSION_QUEUE
    saved = (
        ExtensionManager.stop_event,
        ExtensionManager.extension_thread,
        ExtensionManager.DELAYED_THREADS,
        ExtensionManager.pending_candidate,
        ExtensionManager.current_download_process,
        list(queue.pending_jobs),
        queue.job_running,
    )
    ExtensionManager.stop_event = threading.Event()
    ExtensionManager.extension_thread = None
    ExtensionManager.DELAYED_THREADS = []
    ExtensionManager.pending_candidate = None
    ExtensionManager.current_download_process = None
    yield
    (ExtensionManager.stop_event,
     ExtensionManager.extension_thread,
     ExtensionManager.DELAYED_THREADS,
     ExtensionManager.pending_candidate,
     ExtensionManager.current_download_process,
     queue.pending_jobs,
     queue.job_running) = saved


def _manager():
    """A manager without __init__'s LLM/Prompter/config side effects."""
    manager = ExtensionManager.__new__(ExtensionManager)
    manager.llm = MagicMock()
    manager.prompter = MagicMock()
    manager.ui_callbacks = None
    manager.data_callbacks = None
    manager.extension_wait_min = 1
    manager.extension_wait_expected_max = 1
    return manager


@pytest.mark.unit
class TestRunExtensionsCancellation:
    def test_startup_delay_exits_without_running_a_cycle(self):
        ExtensionManager.stop_event = threading.Event()
        ExtensionManager.stop_event.set()
        manager = _manager()
        manager._extend_by_random_attr = MagicMock()

        started = time.perf_counter()
        manager._run_extensions(initial_sleep=True)

        assert time.perf_counter() - started < 1.0
        manager._extend_by_random_attr.assert_not_called()

    def test_outer_loop_stops_after_the_in_flight_cycle(self):
        """A stop arriving mid-cycle must not be followed by another cycle."""
        ExtensionManager.stop_event = threading.Event()
        manager = _manager()
        calls = []

        def fake_extend(voice=None):
            calls.append(voice)
            ExtensionManager.stop_event.set()

        manager._extend_by_random_attr = fake_extend
        manager.get_extension_sleep_time = lambda _min, _max: 600

        manager._run_extensions(initial_sleep=False)

        assert len(calls) == 1

    def test_idle_wait_is_interrupted_rather_than_slept_through(self):
        """The old code slept in fixed chunks and ignored the flag entirely."""
        ExtensionManager.stop_event = threading.Event()
        manager = _manager()
        entered_idle = threading.Event()

        def fake_extend(voice=None):
            entered_idle.set()

        manager._extend_by_random_attr = fake_extend
        manager.get_extension_sleep_time = lambda _min, _max: 600  # a 10 minute idle

        thread = threading.Thread(
            target=manager._run_extensions, kwargs={"initial_sleep": False}, daemon=True)
        thread.start()
        assert entered_idle.wait(timeout=5.0)

        ExtensionManager.stop_event.set()
        thread.join(timeout=5.0)

        assert not thread.is_alive()


@pytest.mark.unit
class TestDelayedCancellation:
    def test_pending_review_aborts_and_skips_the_download(self):
        ExtensionManager.stop_event = threading.Event()
        ExtensionManager.stop_event.set()
        ExtensionManager.pending_candidate = None
        manager = _manager()
        manager._a = MagicMock()
        manager.get_extension_sleep_time = lambda _min, _max: 1
        candidate = SimpleNamespace(w="id-1", n="Some Track", u={})

        manager._delayed(candidate, None, "query")

        manager._a.assert_not_called()
        assert ExtensionManager.pending_candidate is None


@pytest.mark.unit
class TestJobChainCancellation:
    def test_next_job_is_not_spawned_once_stopped(self, monkeypatch):
        ExtensionManager.stop_event = threading.Event()
        ExtensionManager.stop_event.set()
        manager = _manager()
        spawned = []
        monkeypatch.setattr(
            "extensions.extension_manager.Utils.start_thread",
            lambda *args, **kwargs: spawned.append(args))
        monkeypatch.setattr(
            ExtensionManager.EXTENSION_QUEUE, "take", lambda: ["value", None, False])

        manager._extend(value="value", attr=None)

        assert spawned == []


@pytest.mark.unit
class TestResetAndRestart:
    def test_restart_does_not_revive_the_stopped_generation(self, monkeypatch):
        """The regression this whole mechanism exists to prevent.

        Stop must be permanent for the threads it stopped. A restart installs a
        fresh event rather than clearing the old one, so a thread that was busy
        during the stop still sees its own event set when it resurfaces, and
        exits instead of carrying on beside the newly started thread.
        """
        monkeypatch.setattr(
            "extensions.extension_manager.Utils.start_thread",
            lambda *args, **kwargs: MagicMock(is_alive=lambda: False))
        ExtensionManager.extension_thread = None
        ExtensionManager.DELAYED_THREADS = []
        manager = _manager()

        manager.start_extensions_thread()
        stopped_generation = ExtensionManager.stop_event

        manager.reset_extension(restart_thread=True)

        assert stopped_generation.is_set()
        assert ExtensionManager.stop_event is not stopped_generation
        assert not ExtensionManager.stop_event.is_set()

    def test_stop_without_restart_leaves_the_event_set(self, monkeypatch):
        monkeypatch.setattr(
            "extensions.extension_manager.Utils.start_thread",
            lambda *args, **kwargs: MagicMock(is_alive=lambda: False))
        ExtensionManager.extension_thread = None
        ExtensionManager.DELAYED_THREADS = []
        manager = _manager()
        manager.start_extensions_thread()

        manager.reset_extension(restart_thread=False)

        assert ExtensionManager.stop_event.is_set()
        assert ExtensionManager.extension_thread is None


@pytest.mark.unit
class TestDownloadProcessTermination:
    def test_in_flight_download_is_terminated(self):
        process = MagicMock()
        process.poll.return_value = None
        ExtensionManager.current_download_process = process

        assert ExtensionManager._terminate_download_process() is True

        process.terminate.assert_called_once()
        assert ExtensionManager.current_download_process is None

    def test_killed_when_terminate_is_ignored(self):
        import subprocess

        process = MagicMock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired(cmd="extension download", timeout=5.0), None]
        ExtensionManager.current_download_process = process

        assert ExtensionManager._terminate_download_process() is True

        process.terminate.assert_called_once()
        process.kill.assert_called_once()

    def test_no_process_is_a_no_op(self):
        ExtensionManager.current_download_process = None
        assert ExtensionManager._terminate_download_process() is False

    def test_already_exited_process_is_left_alone(self):
        process = MagicMock()
        process.poll.return_value = 0
        ExtensionManager.current_download_process = process

        assert ExtensionManager._terminate_download_process() is False
        process.terminate.assert_not_called()
