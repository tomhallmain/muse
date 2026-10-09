"""Tests for the bookkeeping in utils/smoke_test.py (the checks themselves run
against a build, from build_exe.py)."""

import logging

import pytest

from utils import smoke_test
from utils.smoke_test import SmokeTest


@pytest.fixture
def log(monkeypatch, caplog):
    """The module logger does not propagate; swap in one caplog sees."""
    monkeypatch.setattr(smoke_test, "logger", logging.getLogger("test_smoke_test"))
    caplog.set_level(logging.INFO, logger="test_smoke_test")
    return caplog


@pytest.mark.unit
class TestSmokeTest:
    def test_passing_checks_give_exit_code_0(self, log):
        smoke = SmokeTest()
        smoke.check("a", True)
        smoke.check_call("b", lambda: "detail")
        assert smoke.failures == []
        assert smoke.result() == 0
        assert "smoke test: b: ok detail" in log.text
        assert "smoke test passed" in log.text

    def test_failed_check_gives_exit_code_1(self, log):
        smoke = SmokeTest()
        smoke.check("a", False, "why")
        assert smoke.failures == ["a"]
        assert smoke.result() == 1
        assert "smoke test: a: FAILED why" in log.text
        assert "smoke test failed: a" in log.text

    def test_exception_fails_the_check_with_its_traceback(self, log):
        def broken():
            raise KeyError(2)

        smoke = SmokeTest()
        smoke.check_call("coqui", broken)
        assert smoke.failures == ["coqui"]
        assert "smoke test: coqui: FAILED KeyError: 2" in log.text
        assert "Traceback" in log.text
        assert "in broken" in log.text

    def test_system_exit_fails_the_check(self, log):
        def exits():
            raise SystemExit("missing metadata")

        smoke = SmokeTest()
        smoke.check_call("metadata", exits)
        assert smoke.failures == ["metadata"]
        assert "SystemExit: missing metadata" in log.text

    def test_non_string_return_value_logs_no_detail(self, log):
        smoke = SmokeTest()
        smoke.check_call("x", lambda: 42)
        assert "smoke test: x: ok" in log.messages

    def test_report_does_not_count_as_a_check(self, log):
        smoke = SmokeTest()
        smoke.report("ffmpeg", "not on PATH")
        assert smoke.failures == []
        assert smoke.result() == 0
