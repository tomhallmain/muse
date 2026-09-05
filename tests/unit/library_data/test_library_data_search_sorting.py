"""Unit tests for LibraryDataSearch result ordering: sort_results_by() and _match_relevance().

These pin the ordering that the search window shows today, so that a later
relevance signal blended into it can be shown not to disturb the tier hierarchy
or the cases that have no sortable field at all.

User data isolation: every track here is an in-memory stub, and neither method
under test reads the filesystem, the library, the cache or the configured
directories -- filepaths below are synthetic strings used only as a tie-break
key. Importing the module pulls in the config and cache singletons, which
tests/bootstrap_env.py has already redirected to a temporary directory.
"""

from types import SimpleNamespace

import pytest

from library_data.library_data import LibraryDataSearch


def _track(filepath="/synthetic/track.mp3", **overrides):
    defaults = dict(
        filepath=filepath,
        searchable_title="", searchable_artist="", searchable_composer="",
        searchable_album="", searchable_genre="",
        get_instrument=lambda: "", get_form=lambda: "", get_catalogue=lambda: "",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.unit
class TestMatchRelevance:
    def test_a_prefix_is_tier_zero(self):
        assert LibraryDataSearch._match_relevance("Beethoven Sonata", "beethoven") == 0

    def test_a_word_boundary_match_is_tier_one(self):
        assert LibraryDataSearch._match_relevance("Piano: Beethoven", "beethoven") == 1

    def test_a_punctuation_boundary_also_counts_as_tier_one(self):
        assert LibraryDataSearch._match_relevance("Piano-Beethoven", "beethoven") == 1

    def test_a_match_inside_a_word_is_tier_two(self):
        assert LibraryDataSearch._match_relevance("XBeethoven", "beethoven") == 2

    def test_no_match_is_tier_two(self):
        assert LibraryDataSearch._match_relevance("Mozart", "beethoven") == 2

    def test_an_empty_value_is_tier_two(self):
        assert LibraryDataSearch._match_relevance("", "beethoven") == 2

    def test_an_empty_query_is_tier_two(self):
        assert LibraryDataSearch._match_relevance("Beethoven", "") == 2

    def test_the_value_is_matched_case_insensitively(self):
        """Queries arrive lowercased from the constructor; values do not."""
        assert LibraryDataSearch._match_relevance("BEETHOVEN", "beethoven") == 0


@pytest.mark.unit
class TestSortResultsBy:
    def test_tiers_order_ahead_of_everything_else(self):
        """A prefix match never sits behind a weaker one, whatever else differs."""
        prefix = _track(searchable_title="beethoven sonata", filepath="/synthetic/3.mp3")
        boundary = _track(searchable_title="piano: beethoven", filepath="/synthetic/2.mp3")
        inside = _track(searchable_title="xbeethoven works", filepath="/synthetic/1.mp3")
        search = LibraryDataSearch(title="beethoven")
        search.results = [inside, boundary, prefix]

        search.sort_results_by()

        assert search.results == [prefix, boundary, inside]

    def test_same_tier_breaks_by_value_then_filepath(self):
        second = _track(searchable_title="beethoven b", filepath="/synthetic/a.mp3")
        first = _track(searchable_title="beethoven a", filepath="/synthetic/z.mp3")
        third = _track(searchable_title="beethoven b", filepath="/synthetic/b.mp3")
        search = LibraryDataSearch(title="beethoven")
        search.results = [third, second, first]

        search.sort_results_by()

        assert search.results == [first, second, third]

    def test_the_field_is_derived_from_the_first_populated_one(self):
        """Derivation walks title, album, artist, composer, genre, instrument,
        form, catalogue and stops at the first, so title decides here."""
        by_title = _track(searchable_title="beethoven", searchable_album="zzz")
        by_album = _track(searchable_title="zzz", searchable_album="beethoven")
        search = LibraryDataSearch(title="beethoven", album="beethoven")
        search.results = [by_album, by_title]

        search.sort_results_by()

        assert search.results == [by_title, by_album]

    def test_an_explicit_attribute_overrides_the_derivation(self):
        by_album = _track(searchable_title="zzz", searchable_album="beethoven")
        by_title = _track(searchable_title="beethoven", searchable_album="zzz")
        search = LibraryDataSearch(title="beethoven", album="beethoven")
        search.results = [by_title, by_album]

        search.sort_results_by(attr="album")

        assert search.results == [by_album, by_title]

    def test_a_callable_attribute_is_invoked(self):
        """instrument, form and catalogue resolve to getters rather than fields."""
        match = _track(get_catalogue=lambda: "bwv 1046", filepath="/synthetic/2.mp3")
        other = _track(get_catalogue=lambda: "k 550", filepath="/synthetic/1.mp3")
        search = LibraryDataSearch(catalogue="bwv")
        search.results = [other, match]

        search.sort_results_by()

        assert search.results == [match, other]

    def test_an_all_field_search_is_left_in_scan_order(self):
        """"all" is absent from the derivation, so these results stay unsorted.
        The guard matters because a relevance signal must not start reordering
        this case by itself."""
        first = _track(searchable_title="zzz", filepath="/synthetic/z.mp3")
        second = _track(searchable_title="beethoven", filepath="/synthetic/a.mp3")
        search = LibraryDataSearch(all="beethoven")
        search.results = [first, second]

        search.sort_results_by()

        assert search.results == [first, second]

    def test_an_empty_result_set_is_tolerated(self):
        search = LibraryDataSearch(title="beethoven")
        search.results = []

        search.sort_results_by()

        assert search.results == []

    def test_a_blank_attribute_leaves_the_order_alone(self):
        first = _track(searchable_title="zzz")
        second = _track(searchable_title="beethoven")
        search = LibraryDataSearch(title="beethoven")
        search.results = [first, second]

        search.sort_results_by(attr="   ")

        assert search.results == [first, second]

    def test_an_unknown_attribute_raises(self):
        search = LibraryDataSearch(title="beethoven")
        search.results = [_track(searchable_title="beethoven")]

        with pytest.raises(Exception, match="Invalid search attribute"):
            search.sort_results_by(attr="all")
