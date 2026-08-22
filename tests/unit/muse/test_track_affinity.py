"""Unit tests for muse/track_affinity.py.

Scores are checked against the default attribute weights, so the expected values
below are derived rather than magic: a reference is normalised by the weight of
the attributes it actually carries.
"""

from types import SimpleNamespace

import pytest

from muse.track_affinity import (
    AFFINITY_OFF,
    AFFINITY_ON,
    DEFAULT_AFFINITY_PREFERENCE,
    DEFAULT_ATTRIBUTE_WEIGHTS,
    AffinityReference,
    affinity,
    affinity_preference,
    favorites_profile,
    reference_for,
)


class _Track:
    """Stand-in exposing the attributes and getters TRACK_VALUE_GETTERS reads."""

    def __init__(self, composer=None, artist=None, album=None, genre=None,
                 form=None, instrument=None, catalogue=None):
        self.composer = composer
        self.album = album
        self._artist = artist
        self._genre = genre
        self._form = form
        self._instrument = instrument
        self._catalogue = catalogue

    def get_main_artist(self):
        return self._artist

    def get_genre(self):
        return self._genre

    def get_form(self):
        return self._form

    def get_instrument(self):
        return self._instrument

    def get_catalogue(self):
        return self._catalogue


def _fav(attribute, value):
    return {"attribute": attribute, "value": value, "timestamp": 1.0}


@pytest.mark.unit
class TestAffinityScoring:
    def test_identical_track_scores_one(self):
        seed = _Track(composer="Mozart", form="Symphony", instrument="Orchestra")
        reference = AffinityReference.from_track(seed)

        assert affinity(seed, reference) == pytest.approx(1.0)

    def test_unrelated_track_scores_zero(self):
        seed = _Track(composer="Mozart", form="Symphony")
        other = _Track(composer="Coltrane", form="Jazz Standard")

        assert affinity(other, AffinityReference.from_track(seed)) == pytest.approx(0.0)

    def test_partial_match_is_weighted(self):
        seed = _Track(composer="Mozart", form="Symphony")
        candidate = _Track(composer="Mozart", form="Concerto")

        expected = DEFAULT_ATTRIBUTE_WEIGHTS["composer"] / (
            DEFAULT_ATTRIBUTE_WEIGHTS["composer"] + DEFAULT_ATTRIBUTE_WEIGHTS["form"])

        assert affinity(candidate, AffinityReference.from_track(seed)) == pytest.approx(expected)

    def test_reference_is_not_penalised_for_attributes_it_lacks(self):
        """A composer-only reference should score a composer match as a full match,
        not as one seventh of the attributes."""
        reference = AffinityReference()
        reference.add("composer", "Mozart")
        candidate = _Track(composer="Mozart", form="Symphony", instrument="Orchestra")

        assert affinity(candidate, reference) == pytest.approx(1.0)

    def test_matching_is_containment_not_equality(self):
        """A query says "mozart" where the tag says the full name."""
        reference = AffinityReference()
        reference.add("composer", "mozart")
        candidate = _Track(composer="Wolfgang Amadeus Mozart")

        assert affinity(candidate, reference) == pytest.approx(1.0)

    def test_empty_reference_scores_zero(self):
        assert affinity(_Track(composer="Mozart"), AffinityReference()) == pytest.approx(0.0)

    def test_none_reference_scores_zero(self):
        assert affinity(_Track(composer="Mozart"), None) == pytest.approx(0.0)

    def test_zero_weighted_attributes_are_ignored(self):
        seed = _Track(composer="Mozart", form="Symphony")
        candidate = _Track(composer="Mozart", form="Concerto")
        weights = dict(DEFAULT_ATTRIBUTE_WEIGHTS, form=0.0)

        assert affinity(candidate, AffinityReference.from_track(seed), weights) == pytest.approx(1.0)

    def test_missing_track_values_do_not_match(self):
        reference = AffinityReference()
        reference.add("composer", "Mozart")

        assert affinity(_Track(), reference) == pytest.approx(0.0)


@pytest.mark.unit
class TestAffinityReference:
    def test_from_track_skips_absent_attributes(self):
        reference = AffinityReference.from_track(_Track(composer="Mozart"))

        assert reference.values["composer"] == {"mozart"}
        assert "form" not in reference.values

    def test_from_search_query_uses_positive_terms(self):
        reference = AffinityReference.from_search_query({"composer": "Mozart, Haydn"})

        assert reference.values["composer"] == {"mozart", "haydn"}

    def test_from_search_query_ignores_negative_terms(self):
        """Negative terms already excluded their tracks from the result set, so
        they cannot affect ordering within it."""
        reference = AffinityReference.from_search_query({"composer": "Mozart, -Haydn"})

        assert reference.values["composer"] == {"mozart"}

    def test_all_field_applies_to_every_attribute(self):
        reference = AffinityReference.from_search_query({"all": "Mozart"})

        assert reference.values["composer"] == {"mozart"}
        assert reference.values["form"] == {"mozart"}

    def test_unknown_query_fields_are_skipped(self):
        reference = AffinityReference.from_search_query({"title": "Jupiter"})

        assert reference.is_empty()

    def test_empty_query_gives_an_empty_reference(self):
        assert AffinityReference.from_search_query(None).is_empty()
        assert AffinityReference.from_search_query({}).is_empty()

    def test_merge_combines_without_mutating_either_side(self):
        first = AffinityReference.from_track(_Track(composer="Mozart"))
        second = AffinityReference.from_track(_Track(composer="Haydn", form="Symphony"))

        merged = first.merge(second)

        assert merged.values["composer"] == {"mozart", "haydn"}
        assert merged.values["form"] == {"symphony"}
        assert first.values["composer"] == {"mozart"}
        assert "form" not in first.values


@pytest.mark.unit
class TestFavoritesProfile:
    def test_orders_values_by_favorite_count(self):
        profile = favorites_profile([
            _fav("composer", "Mozart"),
            _fav("composer", "Haydn"),
            _fav("composer", "Mozart"),
        ])

        assert profile["composer"] == ["Mozart", "Haydn"]

    def test_caps_at_top_n(self):
        raw = [_fav("composer", name) for name in ("A", "B", "C", "D")]
        profile = favorites_profile(raw, top_n=2)

        assert len(profile["composer"]) == 2

    def test_skips_attributes_that_are_not_similarity_signals(self):
        """TITLE identifies one track rather than describing a kind of music."""
        profile = favorites_profile([_fav("title", "Jupiter Symphony")])

        assert profile == {}

    def test_tolerates_junk_entries(self):
        profile = favorites_profile([
            "not a dict",
            {"attribute": "not_an_attribute", "value": "x"},
            {"value": "missing attribute key"},
            _fav("composer", "Mozart"),
        ])

        assert profile == {"composer": ["Mozart"]}

    def test_no_favorites_gives_an_empty_profile(self):
        assert favorites_profile(None) == {}
        assert favorites_profile([]) == {}

    def test_profile_round_trips_into_a_reference(self):
        profile = favorites_profile([_fav("composer", "Mozart")])
        reference = AffinityReference.from_favorites_profile(profile)

        assert affinity(_Track(composer="Mozart"), reference) == pytest.approx(1.0)


@pytest.fixture
def config(isolated_singletons):
    """The isolated config singleton, so setting a preference here is per-test."""
    from utils.config import config as isolated_instance

    return isolated_instance


def _descriptor(search_query=None, allows_resort=True):
    """Stands in for a PlaylistDescriptor, which reference_for only reads two
    things from."""
    return SimpleNamespace(search_query=search_query, allows_resort=lambda: allows_resort)


@pytest.mark.unit
class TestAffinityPreference:
    def test_recognised_values_are_returned(self, config):
        for value in (AFFINITY_OFF, AFFINITY_ON):
            config.affinity_preference = value
            assert affinity_preference() == value

    def test_value_is_normalised(self, config):
        config.affinity_preference = "  ON "

        assert affinity_preference() == AFFINITY_ON

    def test_unrecognised_value_falls_back_to_the_default(self, config):
        """An unset or stale config should still get the working behaviour rather
        than silently disabling the ordering."""
        # "similar" and "varied" are the states this setting used to have, so a
        # config written before the change lands on the working default.
        for value in ("", None, "nonsense", 7, "similar", "varied"):
            config.affinity_preference = value
            assert affinity_preference() == DEFAULT_AFFINITY_PREFERENCE

    def test_the_default_is_active(self):
        assert DEFAULT_AFFINITY_PREFERENCE != AFFINITY_OFF


@pytest.mark.unit
class TestReferenceFor:
    def test_disabled_preference_gives_no_reference(self, config):
        config.affinity_preference = AFFINITY_OFF

        assert reference_for(_descriptor(), _Track(composer="Mozart")) is None

    def test_track_based_playlist_is_left_alone(self, config):
        """Every track was named, so the order is already the listener's decision."""
        config.affinity_preference = AFFINITY_ON

        assert reference_for(_descriptor(allows_resort=False), _Track(composer="Mozart")) is None

    def test_search_query_becomes_the_reference(self, config):
        config.affinity_preference = AFFINITY_ON

        reference = reference_for(_descriptor(search_query={"composer": "Mozart"}))

        assert reference.values["composer"] == {"mozart"}

    def test_start_track_becomes_the_reference(self, config):
        config.affinity_preference = AFFINITY_ON

        reference = reference_for(None, _Track(composer="Mozart", form="Symphony"))

        assert reference.values["composer"] == {"mozart"}
        assert reference.values["form"] == {"symphony"}

    def test_search_and_start_track_combine(self, config):
        config.affinity_preference = AFFINITY_ON

        reference = reference_for(_descriptor(search_query={"composer": "Haydn"}),
                                  _Track(composer="Mozart"))

        assert reference.values["composer"] == {"haydn", "mozart"}

    def test_favorites_apply_only_when_nothing_more_specific_exists(self, config, monkeypatch):
        config.affinity_preference = AFFINITY_ON
        monkeypatch.setattr("muse.track_affinity.current_favorites_profile",
                            lambda: {"composer": ["Bach"]})

        assert reference_for(_descriptor()).values["composer"] == {"bach"}

    def test_favorites_do_not_dilute_a_search(self, config, monkeypatch):
        """A favorite outscoring what was actually searched for would be wrong."""
        config.affinity_preference = AFFINITY_ON
        monkeypatch.setattr("muse.track_affinity.current_favorites_profile",
                            lambda: {"composer": ["Bach"]})

        reference = reference_for(_descriptor(search_query={"composer": "Mozart"}))

        assert reference.values["composer"] == {"mozart"}

    def test_nothing_to_go_on_gives_no_reference(self, config, monkeypatch):
        config.affinity_preference = AFFINITY_ON
        monkeypatch.setattr("muse.track_affinity.current_favorites_profile", lambda: {})

        assert reference_for(_descriptor()) is None
        assert reference_for(None, None) is None

    def test_a_broken_descriptor_does_not_raise(self, config):
        """Any failure must leave the playlist with the order it already had."""
        config.affinity_preference = AFFINITY_ON

        assert reference_for(SimpleNamespace()) is None

    def test_unreadable_favorites_do_not_raise(self, config, monkeypatch):
        config.affinity_preference = AFFINITY_ON
        monkeypatch.setattr("muse.track_affinity.current_favorites_profile",
                            lambda: (_ for _ in ()).throw(RuntimeError("cache gone")))

        assert reference_for(_descriptor()) is None
