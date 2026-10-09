"""Tests for ui_qt/auth/password_utils.require_password.

The root conftest replaces ``require_password`` with a no-op for every test,
so the real decorator is taken from a fresh copy of the module.
"""

import importlib.util

import pytest

import ui_qt.auth.password_utils as patched_module
from utils.globals import ProtectedActions


@pytest.fixture
def password_utils(monkeypatch):
    spec = importlib.util.spec_from_file_location("password_utils_under_test", patched_module.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Grant every check without a dialog or the credential store.
    monkeypatch.setattr(
        module, "check_password_required",
        lambda action_names, master, callback, *args, **kwargs: callback(True),
    )
    return module


@pytest.mark.unit
class TestRequirePassword:
    def test_keeps_the_method_name(self, password_utils):
        """PySide6 mixes up the signal connections of compiled methods with the
        same name: in a build, every menu action ran the last decorated method
        connected while all were named ``wrapper``."""

        class Window:
            @password_utils.require_password(ProtectedActions.EDIT_FAVORITES)
            def open_favorites_window(self):
                """Open favorites."""

        method = Window.open_favorites_window
        assert method.__name__ == "open_favorites_window"
        assert method.__qualname__.endswith("Window.open_favorites_window")
        assert method.__doc__ == "Open favorites."
        assert method.__wrapped__.__name__ == "open_favorites_window"

    def test_runs_the_method_when_granted(self, password_utils):
        class Window:
            master = object()

            @password_utils.require_password(ProtectedActions.EDIT_FAVORITES)
            def open_window(self, value):
                return value * 2

        assert Window().open_window(21) == 42
