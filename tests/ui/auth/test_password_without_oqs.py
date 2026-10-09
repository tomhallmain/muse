"""Tests that password protection fails closed when the stored password needs
OQS this build lacks.

The root conftest replaces ``check_password_required`` and
``PasswordManager.is_security_configured`` for every test, so the real ones
are taken from fresh copies of their modules.
"""

import importlib.util

import pytest

import ui_qt.auth.password_utils as patched_module
from ui_qt.auth.password_core import PasswordManager
from utils.globals import ProtectedActions


class _Config:
    def __init__(self, protected):
        self._protected = protected

    def is_action_protected(self, action_name):
        return action_name in self._protected

    def is_session_timeout_enabled(self):
        return False

    def is_security_advice_enabled(self):
        return False


@pytest.fixture
def password_utils(monkeypatch):
    spec = importlib.util.spec_from_file_location("password_utils_without_oqs", patched_module.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    alerts = []
    monkeypatch.setattr(module, "qt_alert", lambda *args, **kwargs: alerts.append(kwargs.get("kind")))
    monkeypatch.setattr(PasswordManager, "is_password_unreadable", staticmethod(lambda: True))
    monkeypatch.setattr(PasswordManager, "_security_configured_cache", None)
    module.alerts = alerts
    return module


def _use_config(monkeypatch, module, protected):
    monkeypatch.setattr(module, "get_security_config", lambda: _Config(protected))


@pytest.mark.unit
class TestPasswordWithoutOqs:
    def test_counts_as_configured(self, monkeypatch):
        import ui_qt.auth.password_core as patched_core

        spec = importlib.util.spec_from_file_location("password_core_without_oqs", patched_core.__file__)
        core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(core)
        monkeypatch.setattr(core, "stored_keys_need_unavailable_oqs", lambda *args: True)
        assert core.PasswordManager.is_security_configured() is True

    def test_protected_action_is_refused(self, password_utils, monkeypatch):
        _use_config(monkeypatch, password_utils, {ProtectedActions.EDIT_SCHEDULES.value})
        results = []
        returned = password_utils.check_password_required(
            [ProtectedActions.EDIT_SCHEDULES], master=None, callback=results.append)
        assert returned is False
        assert results == [False]
        assert password_utils.alerts == ["error"]

    def test_admin_window_is_refused(self, password_utils, monkeypatch):
        _use_config(monkeypatch, password_utils, {ProtectedActions.ACCESS_ADMIN.value})
        assert password_utils.check_password_required([ProtectedActions.ACCESS_ADMIN], master=None) is False
        assert password_utils.alerts == ["error"]

    def test_unprotected_action_requiring_authentication_is_refused(self, password_utils, monkeypatch):
        _use_config(monkeypatch, password_utils, set())
        returned = password_utils.check_password_required(
            [ProtectedActions.RUN_SEARCH], master=None, allow_unauthenticated=False)
        assert returned is False

    def test_unprotected_action_is_not_refused(self, password_utils, monkeypatch):
        _use_config(monkeypatch, password_utils, set())
        prompts = []

        class Dialog:
            @staticmethod
            def prompt_password(*args, **kwargs):
                prompts.append(args)
                return True

        monkeypatch.setattr(password_utils, "PasswordDialog", Dialog)
        password_utils.check_password_required([ProtectedActions.RUN_SEARCH], master=None)
        assert password_utils.alerts == []
