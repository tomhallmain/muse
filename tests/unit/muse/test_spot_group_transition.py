"""
Tests for MuseSpotProfile group-transition boost and cooldown logic.

Three areas covered:

1. _should_boost_for_group_transition — deterministic helper that decides
   whether the track-speaking and topic chances should be multiplied up.

2. Cooldown suppression — rapid consecutive transitions (e.g. many
   single-track composers) must not all receive the full boost.

3. End-to-end effect on speak_about_prior_track — monkeypatched random
   proves the boost actually changes the flag a caller would observe.
"""
import time
from types import SimpleNamespace

import pytest

from muse import MuseSpotProfile
from utils.globals import TrackResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_prior_profile(spoken_at: float, *, is_group_transition: bool = False) -> SimpleNamespace:
    """Minimal stand-in for a historical MuseSpotProfile.

    Only the fields read by _get_last_spoken_group_transition_profile and
    get_last_spoken_profile are populated.
    """
    p = SimpleNamespace()
    p.was_spoken = True
    p.is_group_transition = is_group_transition
    # Lambda so the value stays relative to "now" regardless of when it is evaluated.
    p.get_time = lambda: spoken_at
    return p


def _make_profile(track, previous_track=None, old_grouping=None, new_grouping=None,
                  prior_profiles=None):
    """Construct a MuseSpotProfile with an optional history chain."""
    prior = prior_profiles or []

    def _callback(idx=0, creation_time=None):
        return prior[idx] if idx < len(prior) else None

    return MuseSpotProfile(
        previous_track=previous_track,
        track_result=TrackResult(track, old_grouping=old_grouping, new_grouping=new_grouping),
        last_track_failed=False,
        skip_track=False,
        grouping_type=None,
        get_previous_spot_profile_callback=_callback,
    )


# ---------------------------------------------------------------------------
# _should_boost_for_group_transition
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestShouldBoostForGroupTransition:

    def test_returns_false_when_not_a_transition(self, mock_tracks):
        profile = _make_profile(mock_tracks[0])
        assert profile._should_boost_for_group_transition(False) is False

    def test_returns_true_for_first_ever_group_transition(self, mock_tracks):
        """No prior history at all — first transition should always get the boost."""
        profile = _make_profile(
            mock_tracks[1],
            previous_track=mock_tracks[0],
            old_grouping="Beethoven",
            new_grouping="Vivaldi",
        )
        assert profile._should_boost_for_group_transition(True) is True

    def test_suppressed_when_last_transition_within_cooldown(self, mock_tracks):
        recent = _mock_prior_profile(
            spoken_at=time.time() - 60,  # 60s ago, well within the 300s cooldown
            is_group_transition=True,
        )
        profile = _make_profile(
            mock_tracks[1],
            previous_track=mock_tracks[0],
            old_grouping="Beethoven",
            new_grouping="Vivaldi",
            prior_profiles=[recent],
        )
        assert profile._should_boost_for_group_transition(True) is False

    def test_applies_when_last_transition_beyond_cooldown(self, mock_tracks):
        old = _mock_prior_profile(
            spoken_at=time.time() - 400,  # 400s ago, past the 300s cooldown
            is_group_transition=True,
        )
        profile = _make_profile(
            mock_tracks[1],
            previous_track=mock_tracks[0],
            old_grouping="Beethoven",
            new_grouping="Vivaldi",
            prior_profiles=[old],
        )
        assert profile._should_boost_for_group_transition(True) is True

    def test_non_transition_spoken_profiles_do_not_reset_cooldown(self, mock_tracks):
        """Only group-transition profiles count for the cooldown window.

        A recently spoken non-transition spot must not suppress the boost.
        """
        recent_ordinary = _mock_prior_profile(
            spoken_at=time.time() - 30,
            is_group_transition=False,
        )
        profile = _make_profile(
            mock_tracks[1],
            previous_track=mock_tracks[0],
            old_grouping="Beethoven",
            new_grouping="Vivaldi",
            prior_profiles=[recent_ordinary],
        )
        # No group-transition profile in history → boost should apply regardless
        assert profile._should_boost_for_group_transition(True) is True


# ---------------------------------------------------------------------------
# End-to-end effect on profile flags
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGroupTransitionBoostEffect:

    def test_is_group_transition_stored_on_profile(self, mock_tracks):
        """Profile must persist is_group_transition so history walkers can find it."""
        with_transition = _make_profile(
            mock_tracks[1],
            previous_track=mock_tracks[0],
            old_grouping="Beethoven",
            new_grouping="Vivaldi",
        )
        without_transition = _make_profile(mock_tracks[0])
        assert with_transition.is_group_transition is True
        assert without_transition.is_group_transition is False

    def test_speak_about_prior_track_boosted_at_transition(self, mock_tracks, monkeypatch):
        """speak_about_prior_track is True at a group transition when a base roll
        would fail but the boosted roll succeeds.

        Roll = 0.4, base chance = 0.3 → 0.4 > 0.3 → normally False.
        Boosted chance = min(1.0, 0.3 * 2.0) = 0.6 → 0.4 < 0.6 → True.
        """
        import random as random_mod

        monkeypatch.setattr(MuseSpotProfile, "chance_speak_after_track", 0.3)
        monkeypatch.setattr(MuseSpotProfile, "chance_speak_before_track", 0.3)
        monkeypatch.setattr(random_mod, "random", lambda: 0.4)

        profile = _make_profile(
            mock_tracks[1],
            previous_track=mock_tracks[0],
            old_grouping="Beethoven",
            new_grouping="Vivaldi",
        )
        assert profile.speak_about_prior_track is True

    def test_speak_about_prior_track_not_boosted_without_transition(self, mock_tracks, monkeypatch):
        """Same roll and base chance, but no transition — flag stays False."""
        import random as random_mod

        monkeypatch.setattr(MuseSpotProfile, "chance_speak_after_track", 0.3)
        monkeypatch.setattr(MuseSpotProfile, "chance_speak_before_track", 0.3)
        monkeypatch.setattr(random_mod, "random", lambda: 0.4)

        profile = _make_profile(
            mock_tracks[1],
            previous_track=mock_tracks[0],
            old_grouping="Beethoven",
            new_grouping="Beethoven",  # same grouping → no transition
        )
        assert profile.speak_about_prior_track is False

    def test_speak_about_prior_track_not_boosted_when_transition_within_cooldown(
        self, mock_tracks, monkeypatch
    ):
        """When the boost is suppressed by cooldown, behaviour matches the no-transition case."""
        import random as random_mod

        monkeypatch.setattr(MuseSpotProfile, "chance_speak_after_track", 0.3)
        monkeypatch.setattr(MuseSpotProfile, "chance_speak_before_track", 0.3)
        monkeypatch.setattr(random_mod, "random", lambda: 0.4)

        recent = _mock_prior_profile(
            spoken_at=time.time() - 60,
            is_group_transition=True,
        )
        profile = _make_profile(
            mock_tracks[1],
            previous_track=mock_tracks[0],
            old_grouping="Beethoven",
            new_grouping="Vivaldi",
            prior_profiles=[recent],
        )
        # Cooldown active → no boost → roll 0.4 > base 0.3 → False
        assert profile.speak_about_prior_track is False
