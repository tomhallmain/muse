"""Unit tests for the catalogue field on library_data.library_data.LibraryDataSearch."""

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
