"""Tests for the favorites-derived leaning appended to the DJ's playlist-context prompt."""

import pytest

from muse import Muse
from muse.track_affinity import AttributeFavorites
from utils.globals import TrackAttribute
from utils.translations import I18N

_ = I18N._


def _profile(monkeypatch, profile):
    monkeypatch.setattr("muse.muse.current_favorites_profile", lambda: profile)


def _favorites(*top, total=None):
    """AttributeFavorites from (value, count) pairs, total defaulting to their sum."""
    return AttributeFavorites(top=list(top), total=total if total is not None else sum(c for _v, c in top))


@pytest.mark.unit
class TestFavoritesPromptSection:
    def test_no_favorites_adds_nothing(self, monkeypatch):
        _profile(monkeypatch, {})

        assert Muse._favorites_prompt_section() == ""

    def test_values_that_recur_are_named(self, monkeypatch):
        _profile(monkeypatch, {"composer": _favorites(("Mozart", 3), ("Haydn", 2))})

        section = Muse._favorites_prompt_section()

        assert _("The listener tends to lean toward:") in section
        assert "Mozart, Haydn" in section

    def test_values_favorited_only_once_each_are_not_a_leaning(self, monkeypatch):
        """Forty favorites spread across forty different composers is no
        favourite composer, even though the attribute itself is well used."""
        spread = _favorites(*[(name, 1) for name in "ABCDE"], total=40)
        _profile(monkeypatch, {"composer": spread})

        assert Muse._favorites_prompt_section() == ""

    def test_an_attribute_barely_used_next_to_another_is_dropped(self, monkeypatch):
        """Someone with forty composer favorites and one genre favorite has a
        taste organised by composer; the genre line is noise."""
        _profile(monkeypatch, {
            "composer": _favorites(("Mozart", 10), ("Haydn", 5), total=40),
            "genre": _favorites(("Jazz", 1)),
        })

        section = Muse._favorites_prompt_section()

        assert "Mozart" in section
        assert "Jazz" not in section
        assert TrackAttribute.GENRE.get_translation() not in section

    def test_at_most_two_examples_are_named(self, monkeypatch):
        _profile(monkeypatch, {"composer": _favorites(("A", 5), ("B", 4), ("C", 3))})

        section = Muse._favorites_prompt_section()

        assert "A, B" in section
        assert "C" not in section

    def test_attribute_labels_are_translated(self, monkeypatch):
        """The section is appended to a prompt that was already loaded in the
        listener's language, so the labels have to match it."""
        _profile(monkeypatch, {"composer": _favorites(("Mozart", 2))})

        assert TrackAttribute.COMPOSER.get_translation() in Muse._favorites_prompt_section()

    def test_unknown_attributes_fall_back_to_their_raw_name(self, monkeypatch):
        _profile(monkeypatch, {"not_an_attribute": _favorites(("Something", 2))})

        assert "not_an_attribute: Something" in Muse._favorites_prompt_section()

    def test_section_starts_on_its_own_block(self, monkeypatch):
        """It is concatenated onto a formatted prompt, so it has to separate
        itself rather than run into the previous line."""
        _profile(monkeypatch, {"composer": _favorites(("Mozart", 2))})

        assert Muse._favorites_prompt_section().startswith("\n\n")

    def test_attributes_are_ordered_stably(self, monkeypatch):
        _profile(monkeypatch, {
            "genre": _favorites(("Jazz", 2)),
            "composer": _favorites(("Mozart", 2)),
            "artist": _favorites(("Gould", 2)),
        })

        section = Muse._favorites_prompt_section()
        labels = [TrackAttribute(a).get_translation() for a in ("artist", "composer", "genre")]
        positions = [section.index(label) for label in labels]

        assert positions == sorted(positions)
