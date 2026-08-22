"""Tests for the favorites section appended to the DJ's playlist-context prompt."""

import pytest

from muse import Muse
from utils.globals import TrackAttribute
from utils.translations import I18N

_ = I18N._


def _profile(monkeypatch, profile):
    monkeypatch.setattr("muse.muse.current_favorites_profile", lambda: profile)


@pytest.mark.unit
class TestFavoritesPromptSection:
    def test_no_favorites_adds_nothing(self, monkeypatch):
        _profile(monkeypatch, {})

        assert Muse._favorites_prompt_section() == ""

    def test_values_are_listed_per_attribute(self, monkeypatch):
        _profile(monkeypatch, {"composer": ["Mozart", "Haydn"]})

        section = Muse._favorites_prompt_section()

        assert _("What the listener has marked as a favorite:") in section
        assert "Mozart, Haydn" in section

    def test_attribute_labels_are_translated(self, monkeypatch):
        """The section is appended to a prompt that was already loaded in the
        listener's language, so the labels have to match it."""
        _profile(monkeypatch, {"composer": ["Mozart"]})

        assert TrackAttribute.COMPOSER.get_translation() in Muse._favorites_prompt_section()

    def test_unknown_attributes_fall_back_to_their_raw_name(self, monkeypatch):
        _profile(monkeypatch, {"not_an_attribute": ["Something"]})

        assert "not_an_attribute: Something" in Muse._favorites_prompt_section()

    def test_section_starts_on_its_own_block(self, monkeypatch):
        """It is concatenated onto a formatted prompt, so it has to separate
        itself rather than run into the previous line."""
        _profile(monkeypatch, {"composer": ["Mozart"]})

        assert Muse._favorites_prompt_section().startswith("\n\n")

    def test_attributes_are_ordered_stably(self, monkeypatch):
        _profile(monkeypatch, {"genre": ["Jazz"], "composer": ["Mozart"], "artist": ["Gould"]})

        section = Muse._favorites_prompt_section()
        labels = [TrackAttribute(a).get_translation() for a in ("artist", "composer", "genre")]
        positions = [section.index(label) for label in labels]

        assert positions == sorted(positions)
