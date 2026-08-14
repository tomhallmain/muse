"""Unit tests for library_data.library_data.LibraryDataSearch: the catalogue field and negative-search terms."""

from types import SimpleNamespace

from library_data.library_data import LibraryDataSearch
from utils.globals import PlaylistSortType


def _stub_track(catalogue="beethoven sonatas"):
    return SimpleNamespace(
        searchable_title="", searchable_artist="", searchable_composer="",
        searchable_album="", searchable_genre="",
        get_instrument=lambda: "", get_form=lambda: "",
        get_catalogue=lambda: catalogue,
    )


def _track(**overrides):
    defaults = dict(
        searchable_title="", searchable_artist="", searchable_composer="",
        searchable_album="", searchable_genre="",
        get_instrument=lambda: "", get_form=lambda: "",
        get_catalogue=lambda: "",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_catalogue_field_defaults_empty():
    search = LibraryDataSearch()
    assert search.catalogue == ""


def test_catalogue_field_is_lowercased():
    search = LibraryDataSearch(catalogue="Beethoven Sonatas")
    assert search.catalogue == "beethoven sonatas"


def test_is_valid_true_for_catalogue_only():
    search = LibraryDataSearch(catalogue="beethoven sonatas")
    assert search.is_valid()


def test_test_matches_track_by_catalogue():
    search = LibraryDataSearch(catalogue="beethoven sonatas")
    assert search.test(_stub_track("beethoven sonatas")) is True


def test_test_rejects_non_matching_catalogue():
    search = LibraryDataSearch(catalogue="beethoven sonatas")
    assert search.test(_stub_track("vivaldi: the four seasons")) is False


def test_get_playlist_sort_type_catalogue():
    search = LibraryDataSearch(catalogue="beethoven sonatas")
    assert search.get_playlist_sort_type() == PlaylistSortType.CATALOGUE_SHUFFLE


def test_get_inferred_sort_type_catalogue():
    search = LibraryDataSearch(catalogue="beethoven sonatas")
    assert search.get_inferred_sort_type() == PlaylistSortType.CATALOGUE_SHUFFLE


def test_get_inferred_sort_type_prefers_broader_scope_over_catalogue():
    search = LibraryDataSearch(catalogue="beethoven sonatas", composer="beethoven")
    assert search.get_inferred_sort_type() == PlaylistSortType.COMPOSER_SHUFFLE


def test_to_json_round_trip_includes_catalogue():
    search = LibraryDataSearch(catalogue="beethoven sonatas")
    data = search.to_json()
    assert data["catalogue"] == "beethoven sonatas"
    restored = LibraryDataSearch.from_json(data)
    assert restored.catalogue == "beethoven sonatas"


class TestParseTerms:
    def test_single_positive_term(self):
        assert LibraryDataSearch._parse_terms("beethoven") == (["beethoven"], [])

    def test_single_negative_term(self):
        assert LibraryDataSearch._parse_terms("-piano") == ([], ["piano"])

    def test_mixed_positive_and_negative(self):
        assert LibraryDataSearch._parse_terms("beethoven, -piano") == (["beethoven"], ["piano"])

    def test_whitespace_around_commas_and_dashes_is_stripped(self):
        assert LibraryDataSearch._parse_terms("  beethoven ,  - piano  ") == (["beethoven"], ["piano"])

    def test_bare_dash_is_dropped(self):
        assert LibraryDataSearch._parse_terms("-") == ([], [])

    def test_empty_field_yields_no_terms(self):
        assert LibraryDataSearch._parse_terms("") == ([], [])

    def test_multiple_positive_terms(self):
        assert LibraryDataSearch._parse_terms("beethoven, mozart") == (["beethoven", "mozart"], [])


class TestFieldNegativeSearch:
    def test_positive_term_matches_like_before(self):
        search = LibraryDataSearch(artist="beethoven")
        assert search.test(_track(searchable_artist="ludwig van beethoven")) is True

    def test_negative_term_excludes_matching_track(self):
        search = LibraryDataSearch(title="symphony, -piano")
        assert search.test(_track(searchable_title="piano symphony no. 5")) is False

    def test_negative_term_allows_non_matching_track(self):
        search = LibraryDataSearch(title="symphony, -piano")
        assert search.test(_track(searchable_title="symphony no. 5 for orchestra")) is True

    def test_multiple_positive_terms_all_required(self):
        search = LibraryDataSearch(title="symphony, no. 5")
        assert search.test(_track(searchable_title="symphony no. 9")) is False
        assert search.test(_track(searchable_title="symphony no. 5")) is True

    def test_negative_only_field_excludes_by_absence(self):
        search = LibraryDataSearch(genre="-jazz")
        assert search.test(_track(searchable_genre="jazz fusion")) is False
        assert search.test(_track(searchable_genre="classical")) is True

    def test_missing_attribute_never_matches_regardless_of_polarity(self):
        search = LibraryDataSearch(genre="-jazz")
        assert search.test(_track(searchable_genre="")) is False
        assert search.test(_track(searchable_genre=None)) is False


class TestAllFieldsNegativeSearch:
    def test_negative_term_excludes_across_every_searched_attribute(self):
        search = LibraryDataSearch(all="beethoven, -piano")
        track = _track(searchable_artist="ludwig van beethoven", searchable_genre="piano concerto")
        assert search.test(track) is False

    def test_positive_and_negative_combo_matches_when_negative_absent(self):
        search = LibraryDataSearch(all="beethoven, -piano")
        track = _track(searchable_artist="ludwig van beethoven", searchable_genre="orchestral")
        assert search.test(track) is True

    def test_negative_only_matches_by_absence(self):
        search = LibraryDataSearch(all="-piano")
        assert search.test(_track(searchable_genre="orchestral")) is True
        assert search.test(_track(searchable_genre="piano concerto")) is False
