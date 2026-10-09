"""Tests for utils/crash_log.py. faulthandler itself is replaced, so pytest's
own fault handler stays in place."""

import os

import pytest

from utils import crash_log


@pytest.fixture
def fault_log(monkeypatch, tmp_path):
    """A fresh module state with logs in tmp_path; records faulthandler.enable calls."""
    monkeypatch.setenv("MUSE_APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(crash_log, "_fault_log", None)
    calls = []
    monkeypatch.setattr(crash_log.faulthandler, "enable", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(crash_log, "describe", lambda: "Muse 9.9 (test)")
    yield calls
    if crash_log._fault_log is not None:
        crash_log._fault_log.close()


def _log_path(tmp_path):
    return os.path.join(str(tmp_path), "logs", crash_log.FAULT_LOG_NAME)


@pytest.mark.unit
class TestEnableFaultLog:
    def test_enables_faulthandler_on_the_log_file(self, fault_log, tmp_path):
        path = crash_log.enable_fault_log()
        assert path == _log_path(tmp_path)
        assert len(fault_log) == 1
        assert fault_log[0]["file"] is crash_log._fault_log
        assert fault_log[0]["all_threads"] is True

    def test_writes_one_start_line(self, fault_log, tmp_path):
        crash_log.enable_fault_log()
        with open(_log_path(tmp_path), encoding="utf-8") as f:
            lines = f.read().splitlines()
        assert len(lines) == 1
        assert lines[0].startswith("--- started ")
        assert f"pid {os.getpid()}" in lines[0]
        assert lines[0].endswith("Muse 9.9 (test)")

    def test_second_call_reuses_the_open_file(self, fault_log):
        first = crash_log.enable_fault_log()
        assert crash_log.enable_fault_log() == first
        assert len(fault_log) == 1

    def test_appends_to_a_small_log(self, fault_log, tmp_path):
        os.makedirs(os.path.dirname(_log_path(tmp_path)))
        with open(_log_path(tmp_path), "w", encoding="utf-8") as f:
            f.write("earlier fault\n")
        crash_log.enable_fault_log()
        crash_log._fault_log.flush()
        with open(_log_path(tmp_path), encoding="utf-8") as f:
            assert f.read().startswith("earlier fault\n")

    def test_starts_afresh_past_the_size_limit(self, fault_log, tmp_path, monkeypatch):
        monkeypatch.setattr(crash_log, "MAX_FAULT_LOG_BYTES", 10)
        os.makedirs(os.path.dirname(_log_path(tmp_path)))
        with open(_log_path(tmp_path), "w", encoding="utf-8") as f:
            f.write("x" * 100)
        crash_log.enable_fault_log()
        with open(_log_path(tmp_path), encoding="utf-8") as f:
            assert f.read().startswith("--- started ")
