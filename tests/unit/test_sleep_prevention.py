"""Unit tests for lib.sleep_prevention.

Focused on the parts that were adjusted when porting the module from
sd-runner: the app identifier this process files state under, the
app-independent shared state directory that lets several applications see
each other's totals, and the refcount/effective-mask semantics.

Every test redirects the state directory to a tmp_path and stubs the OS hook,
so nothing here touches the real machine-local state file or spawns a real
systemd-inhibit / caffeinate process.
"""

import json
import os
import sys

import pytest

import lib.sleep_prevention as sp
from utils.globals import AppInfo


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Point the module at a scratch state dir with the OS hook disabled."""
    monkeypatch.setenv(sp._STATE_DIR_ENV_VAR, str(tmp_path / "state"))
    monkeypatch.setattr(sp, "_apply_os", lambda effective: None)
    # Module-level state persists across tests in the same process.
    monkeypatch.setattr(sp, "_local_refs", {"SYSTEM": 0, "DISPLAY": 0})
    monkeypatch.setattr(sp, "_bootstrapped", False)
    monkeypatch.setattr(sp, "_prev_effective", None)
    monkeypatch.setattr(sp, "_app_id_cache", None)
    yield


def _read_state() -> dict:
    with open(sp.state_path()) as handle:
        return json.load(handle)


class TestApplicationIdentity:
    def test_files_state_under_this_application(self):
        """Not the source project's id -- a wrong value is silent and misfiles rows."""
        assert sp._app_identifier() == AppInfo.APP_IDENTIFIER
        assert sp._app_identifier() == "muse"

    def test_falls_back_without_adopting_another_app(self, monkeypatch):
        """A None entry in sys.modules makes the lazy import raise ImportError."""
        monkeypatch.setitem(sys.modules, "utils.globals", None)
        assert sp._app_identifier() == sp._FALLBACK_APP_ID
        # The fallback must name this app, not the project ported from.
        assert sp._FALLBACK_APP_ID == "muse"


class TestStateDirIsShared:
    def test_env_override_is_honoured(self, tmp_path):
        assert sp.state_dir() == str(tmp_path / "state")

    def test_resolved_path_carries_no_application_name(self, monkeypatch):
        """The per-app dimension belongs inside the JSON, not in the path --
        an app-namespaced directory makes cross-app totals unreachable."""
        monkeypatch.delenv(sp._STATE_DIR_ENV_VAR, raising=False)
        resolved = sp.state_dir()
        for app_id in ("weidr", "sd_runner", "muse"):
            assert app_id not in resolved

    def test_state_file_sits_in_the_state_dir(self):
        assert os.path.dirname(sp.state_path()) == sp.state_dir()


class TestWakeLevelSemantics:
    def test_full_is_system_or_display(self):
        assert sp.WakeLevel.FULL == sp.WakeLevel.SYSTEM | sp.WakeLevel.DISPLAY

    def test_display_implies_system(self):
        assert sp.effective_wake({"SYSTEM": 0, "DISPLAY": 1}) == sp.WakeLevel.FULL

    def test_system_alone_does_not_imply_display(self):
        assert sp.effective_wake({"SYSTEM": 1, "DISPLAY": 0}) == sp.WakeLevel.SYSTEM

    def test_no_refs_is_none(self):
        assert sp.effective_wake({"SYSTEM": 0, "DISPLAY": 0}) == sp.WakeLevel.NONE


class TestAcquireRelease:
    def test_acquire_release_round_trip(self):
        sp.acquire_wake(sp.WakeLevel.SYSTEM)
        assert sp.effective_wake() == sp.WakeLevel.SYSTEM
        sp.release_wake(sp.WakeLevel.SYSTEM)
        assert sp.effective_wake() == sp.WakeLevel.NONE

    def test_nested_acquires_need_matching_releases(self):
        sp.acquire_wake(sp.WakeLevel.SYSTEM)
        sp.acquire_wake(sp.WakeLevel.SYSTEM)
        sp.release_wake(sp.WakeLevel.SYSTEM)
        assert sp.effective_wake() == sp.WakeLevel.SYSTEM  # still held
        sp.release_wake(sp.WakeLevel.SYSTEM)
        assert sp.effective_wake() == sp.WakeLevel.NONE

    def test_unbalanced_release_is_ignored(self):
        """No negative refcounts -- a stray release must not disarm a real hold."""
        sp.release_wake(sp.WakeLevel.SYSTEM)
        assert sp.ref_count() == 0
        sp.acquire_wake(sp.WakeLevel.SYSTEM)
        assert sp.effective_wake() == sp.WakeLevel.SYSTEM
        sp.release_wake(sp.WakeLevel.SYSTEM)

    def test_hold_wake_releases_on_exception(self):
        with pytest.raises(RuntimeError):
            with sp.hold_wake(sp.WakeLevel.SYSTEM):
                assert sp.effective_wake() == sp.WakeLevel.SYSTEM
                raise RuntimeError("boom")
        assert sp.effective_wake() == sp.WakeLevel.NONE


class TestSharedStateAcrossApplications:
    def test_this_app_row_is_written_and_cleared(self):
        sp.acquire_wake(sp.WakeLevel.SYSTEM)
        requests = _read_state()["prevention_requests"]
        assert requests[AppInfo.APP_IDENTIFIER][str(os.getpid())]["SYSTEM"] == 1

        sp.release_wake(sp.WakeLevel.SYSTEM)
        # An emptied row is dropped rather than left at zero.
        assert AppInfo.APP_IDENTIFIER not in _read_state()["prevention_requests"]

    def test_totals_aggregate_across_applications(self):
        """The point of the shared file: one app can see another's holds."""
        sp.acquire_wake(sp.WakeLevel.SYSTEM)
        try:
            data = _read_state()
            # A second application holding two SYSTEM requests. Keyed to this
            # PID so the liveness prune keeps it.
            live_pid = str(os.getpid())
            data["prevention_requests"]["other_app"] = {live_pid: {"SYSTEM": 2, "DISPLAY": 0}}
            data["capable_instances"]["other_app"] = {live_pid: 1}
            with open(sp.state_path(), "w") as handle:
                json.dump(data, handle)

            assert sp.aggregate_prevention_count() == 3  # 1 ours + 2 theirs
            assert sp.live_instance_count() == 2
        finally:
            sp.release_wake(sp.WakeLevel.SYSTEM)

    def test_other_app_holds_do_not_change_local_refs(self):
        """OS hooks stay process-local: another app's count must not keep this
        process's own inhibitor asserted after its work is done."""
        data = sp._empty_state()
        data["prevention_requests"]["other_app"] = {str(os.getpid()): {"SYSTEM": 5, "DISPLAY": 0}}
        data["capable_instances"]["other_app"] = {str(os.getpid()): 1}
        os.makedirs(sp.state_dir(), exist_ok=True)
        with open(sp.state_path(), "w") as handle:
            json.dump(data, handle)

        sp.acquire_wake(sp.WakeLevel.SYSTEM)
        sp.release_wake(sp.WakeLevel.SYSTEM)
        assert sp.effective_wake() == sp.WakeLevel.NONE
        assert sp.ref_count() == 0

    def test_dead_process_rows_are_pruned(self, monkeypatch):
        live_pid = str(os.getpid())
        dead_pid = str(os.getpid() + 1)
        monkeypatch.setattr(sp, "_pid_is_alive", lambda pid: str(pid) == live_pid)

        requests = {
            "weidr": {live_pid: {"SYSTEM": 1, "DISPLAY": 0}},
            "other_app": {dead_pid: {"SYSTEM": 4, "DISPLAY": 0}},
        }
        capable = {"weidr": {live_pid: 1}, "other_app": {dead_pid: 1}}
        sp._prune_nested_maps(requests, capable)

        assert "other_app" not in requests
        assert requests["weidr"][live_pid]["SYSTEM"] == 1


class TestCaffeinateEndsWithThisProcess:
    """Without -w, a process that is killed or crashes skips its atexit release
    and leaves caffeinate asserting forever."""

    @pytest.mark.parametrize("level", [sp.WakeLevel.SYSTEM, sp.WakeLevel.DISPLAY, sp.WakeLevel.FULL])
    def test_waits_on_this_pid(self, monkeypatch, level):
        monkeypatch.setattr(sp.shutil, "which", lambda name: "/usr/bin/caffeinate")
        argv = sp._darwin_argv_for(level)
        assert argv[-2:] == ("-w", str(os.getpid()))

    def test_no_process_for_none(self, monkeypatch):
        monkeypatch.setattr(sp.shutil, "which", lambda name: "/usr/bin/caffeinate")
        assert sp._darwin_argv_for(sp.WakeLevel.NONE) is None
