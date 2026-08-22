"""Tests for biasing random extensions toward the listener's favorites."""

import pytest

from extensions.extension_manager import ExtensionManager
from utils.globals import TrackAttribute


def _manager():
    return ExtensionManager.__new__(ExtensionManager)


@pytest.fixture
def always_bias(monkeypatch):
    monkeypatch.setattr("extensions.extension_manager.random.random", lambda: 0.0)


@pytest.fixture
def never_bias(monkeypatch):
    monkeypatch.setattr("extensions.extension_manager.random.random", lambda: 1.0)


def _profile(monkeypatch, profile):
    monkeypatch.setattr("extensions.extension_manager.current_favorites_profile", lambda: profile)


@pytest.mark.unit
class TestFavoredValue:
    def test_returns_a_favorite_for_the_attribute(self, monkeypatch, always_bias):
        _profile(monkeypatch, {"composer": ["Mozart"]})

        assert _manager()._favored_value(TrackAttribute.COMPOSER) == "Mozart"

    def test_ignores_favorites_for_other_attributes(self, monkeypatch, always_bias):
        _profile(monkeypatch, {"composer": ["Mozart"]})

        assert _manager()._favored_value(TrackAttribute.GENRE) is None

    def test_no_favorites_means_no_preference(self, monkeypatch, always_bias):
        _profile(monkeypatch, {})

        assert _manager()._favored_value(TrackAttribute.COMPOSER) is None

    def test_the_bias_does_not_always_apply(self, monkeypatch, never_bias):
        """Always drawing from a handful of favored values would keep returning
        the same few and stop turning up anything new."""
        _profile(monkeypatch, {"composer": ["Mozart"]})

        assert _manager()._favored_value(TrackAttribute.COMPOSER) is None

    def test_bias_chance_is_partial(self):
        assert 0.0 < ExtensionManager.FAVORITE_BIAS_CHANCE < 1.0

    def test_unreadable_favorites_do_not_raise(self, monkeypatch, always_bias):
        """current_favorites_profile swallows its own failures, so a missing or
        broken cache reads as no preference rather than breaking the extension."""
        _profile(monkeypatch, {})

        assert _manager()._favored_value(TrackAttribute.ARTIST) is None
