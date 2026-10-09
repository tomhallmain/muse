"""Tests for tts/providers/typeguard_fallback.py, the pass-through
``typechecked`` a compiled build uses."""

import pytest

from tts.providers import typeguard_fallback


def _function(x: int) -> int:
    return x


@pytest.mark.unit
class TestTypechecked:
    def test_bare_decorator_returns_the_function(self):
        assert typeguard_fallback.typechecked(_function) is _function

    def test_with_options_returns_the_function(self):
        assert typeguard_fallback.typechecked(typecheck_fail_callback=None)(_function) is _function

    def test_no_type_check_happens(self):
        assert typeguard_fallback.typechecked(_function)("not an int") == "not an int"


@pytest.mark.unit
class TestInstall:
    def test_replaces_typechecked(self, monkeypatch):
        typeguard = pytest.importorskip("typeguard")
        decorators = pytest.importorskip("typeguard._decorators")
        # Registered with their current values so monkeypatch restores them.
        monkeypatch.setattr(typeguard, "typechecked", typeguard.typechecked)
        monkeypatch.setattr(decorators, "typechecked", decorators.typechecked)
        typeguard_fallback.install()
        assert typeguard.typechecked is decorators.typechecked is typeguard_fallback.typechecked
