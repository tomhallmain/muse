"""Unit tests for saturation in muse/track_affinity.py.

Saturation answers "what has the listener had enough of", measured in listening
time. The log is process-wide, so every test here clears it first.
"""

from types import SimpleNamespace

import pytest

from muse.track_affinity import (
    SATURATION_HALF_LIFE_SECONDS,
    SATURATION_SECONDS_THRESHOLD,
    affinity,
    clear_listening_log,
    record_listening,
    saturation_applies,
    saturation_reference,
)


class _Track:
    def __init__(self, composer=None, artist=None, seconds=300.0):
        self.composer = composer
        self.artist = artist
        self.album = None
        self._seconds = seconds

    def get_track_length(self):
        return self._seconds

    def get_main_artist(self):
        raise AssertionError("the resolved main artist is derived lazily and must not be forced")

    def get_genre(self):
        return None

    def get_form(self):
        return None

    def get_instrument(self):
        return None

    def get_catalogue(self):
        return None


def _descriptor(track_based=False, search_based=False):
    return SimpleNamespace(is_track_based=lambda: track_based,
                           is_search_based=lambda: search_based)


@pytest.fixture(autouse=True)
def clean_log():
    clear_listening_log()
    yield
    clear_listening_log()


@pytest.mark.unit
class TestSaturationApplies:
    def test_no_descriptor_is_the_press_play_case(self):
        """The attribute is only ever set for a saved playlist, so plain press-play
        arrives here as None -- and it is the case saturation exists for."""
        assert saturation_applies(None) is True

    def test_a_directory_playlist_is_treated_the_same(self):
        assert saturation_applies(_descriptor()) is True

    def test_a_search_playlist_is_left_alone(self):
        assert saturation_applies(_descriptor(search_based=True)) is False

    def test_a_track_playlist_is_left_alone(self):
        assert saturation_applies(_descriptor(track_based=True)) is False

    def test_an_unreadable_descriptor_leaves_it_off(self):
        assert saturation_applies(SimpleNamespace()) is False


@pytest.mark.unit
class TestListeningLog:
    def test_nothing_heard_means_nothing_to_avoid(self):
        assert saturation_reference() is None

    def test_one_short_track_does_not_saturate(self):
        record_listening(_Track(composer="Mozart", seconds=240.0))

        assert saturation_reference() is None

    def test_one_long_track_saturates(self):
        """The case from the card: a long track counts for as much as the several
        short ones it displaced."""
        record_listening(_Track(composer="Mozart", seconds=SATURATION_SECONDS_THRESHOLD + 1))

        reference = saturation_reference()
        assert reference is not None
        assert reference.values["composer"] == {"mozart"}

    def test_time_accumulates_across_tracks(self):
        for _ in range(3):
            record_listening(_Track(composer="Mozart", seconds=SATURATION_SECONDS_THRESHOLD / 2))

        assert saturation_reference().values["composer"] == {"mozart"}

    def test_only_the_over_heard_value_is_included(self):
        record_listening(_Track(composer="Mozart", seconds=SATURATION_SECONDS_THRESHOLD + 1))
        record_listening(_Track(composer="Haydn", seconds=60.0))

        assert saturation_reference().values["composer"] == {"mozart"}

    def test_saturation_decays(self):
        import muse.track_affinity as module

        record_listening(_Track(composer="Mozart", seconds=SATURATION_SECONDS_THRESHOLD * 1.5))
        assert saturation_reference() is not None

        # Push the entry far enough into the past that its weight halves twice.
        entry = module._listening_log["composer"]["mozart"]
        entry[1] -= SATURATION_HALF_LIFE_SECONDS * 2

        assert saturation_reference() is None

    def test_the_plain_artist_tag_is_used(self):
        """_Track raises from get_main_artist: recording every track must not force
        a derivation only one shuffle needs."""
        record_listening(_Track(artist="Glenn Gould", seconds=SATURATION_SECONDS_THRESHOLD + 1))

        assert saturation_reference().values["artist"] == {"glenn gould"}

    def test_a_track_with_no_length_is_not_recorded(self):
        record_listening(_Track(composer="Mozart", seconds=0.0))

        assert saturation_reference() is None

    def test_a_broken_track_does_not_raise(self):
        record_listening(SimpleNamespace())

        assert saturation_reference() is None

    def test_an_explicit_duration_overrides_the_track_length(self):
        record_listening(_Track(composer="Mozart", seconds=1.0),
                         seconds=SATURATION_SECONDS_THRESHOLD + 1)

        assert saturation_reference() is not None

    def test_the_reference_scores_like_any_other(self):
        """Saturation reuses the same measure, which is what lets one score serve
        both directions."""
        record_listening(_Track(composer="Mozart", seconds=SATURATION_SECONDS_THRESHOLD + 1))
        reference = saturation_reference()

        assert affinity(_Track(composer="Mozart"), reference) == pytest.approx(1.0)
        assert affinity(_Track(composer="Coltrane"), reference) == pytest.approx(0.0)
