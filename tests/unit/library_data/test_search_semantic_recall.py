"""Unit tests for pulling tracks into a search that the substring filter rejected.

The store is stubbed, so what is under test is the integration: which searches
get the pass at all, what is filtered back out of what it returns, and where the
results it adds end up in the order. The store's own behaviour -- building,
persistence, cutoffs -- is covered in test_track_embedding_store.py.

User data isolation: every track is an in-memory stub, the store is a stub that
touches no disk, and nothing here reads the library or the real caches.
"""

import inspect
from types import SimpleNamespace

import pytest

from library_data import library_data as library_data_module
from library_data.library_data import LibraryData, LibraryDataSearch
from utils.config import config


def _track(filepath, **overrides):
    defaults = dict(
        filepath=filepath,
        searchable_title="", searchable_artist="", searchable_composer="",
        searchable_album="", searchable_genre="",
        get_instrument=lambda: "", get_form=lambda: "", get_catalogue=lambda: "",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class _FakeStore:
    """Answers with fixed matches and records that it was asked to stay current."""

    def __init__(self, matches):
        self.matches = matches
        self.built_for = None
        self.queried = []

    def ensure_built(self, field, tracks, track_attr, status_callback=None):
        self.built_for = (field, len(tracks), track_attr)

    def query(self, field, text):
        self.queried.append((field, text))
        return list(self.matches)


@pytest.fixture
def index_for(monkeypatch):
    """Install a stub store and return the handle to inspect afterwards."""
    monkeypatch.setattr(library_data_module, "semantic_recall_enabled", lambda: True)
    monkeypatch.setattr(library_data_module, "semantic_fields", lambda: ("title", "artist", "album"))

    def install(matches):
        store = _FakeStore(matches)
        monkeypatch.setattr(library_data_module, "get_store", lambda: store)
        return store

    return install


@pytest.mark.unit
class TestWhichSearchesGetThePass:
    def test_a_configured_field_pulls_in_what_the_filter_missed(self, index_for):
        literal = _track("/synthetic/1.mp3", searchable_title="beethoven sonata")
        missed = _track("/synthetic/2.mp3", searchable_title="beethovn concerto")
        index = index_for([("/synthetic/2.mp3", 0.93)])
        search = LibraryDataSearch(title="beethoven")
        search.results = [literal]

        LibraryData._add_semantic_results(search, [literal, missed])

        assert search.results == [literal, missed]
        assert index.queried == [("title", "beethoven")], "the query goes in unlabelled"
        assert index.built_for == ("title", 2, "searchable_title")

    def test_a_later_page_adds_nothing(self, index_for):
        """Page two would duplicate what page one added or reshuffle it."""
        literal = _track("/synthetic/1.mp3", searchable_title="beethoven sonata")
        missed = _track("/synthetic/2.mp3", searchable_title="beethovn concerto")
        index = index_for([("/synthetic/2.mp3", 0.93)])
        search = LibraryDataSearch(title="beethoven")
        search.offset = 200
        search.results = [literal]

        LibraryData._add_semantic_results(search, [literal, missed])

        assert search.results == [literal]
        assert index.queried == []

    def test_an_unconfigured_field_is_left_alone(self, monkeypatch, index_for):
        literal = _track("/synthetic/1.mp3", searchable_composer="beethoven")
        missed = _track("/synthetic/2.mp3", searchable_composer="beethovn")
        index = index_for([("/synthetic/2.mp3", 0.93)])
        monkeypatch.setattr(library_data_module, "semantic_fields", lambda: ("title",))
        search = LibraryDataSearch(composer="beethoven")
        search.results = [literal]

        LibraryData._add_semantic_results(search, [literal, missed])

        assert search.results == [literal]
        assert index.queried == []

    def test_an_all_search_is_left_alone(self, index_for):
        """"all" has no single field to have built an index for."""
        literal = _track("/synthetic/1.mp3", searchable_title="beethoven sonata")
        index = index_for([("/synthetic/2.mp3", 0.93)])
        search = LibraryDataSearch(all="beethoven")
        search.results = [literal]

        LibraryData._add_semantic_results(search, [literal])

        assert search.results == [literal]
        assert index.queried == []

    def test_the_config_flag_turns_the_pass_off(self, monkeypatch, index_for):
        literal = _track("/synthetic/1.mp3", searchable_title="beethoven sonata")
        missed = _track("/synthetic/2.mp3", searchable_title="beethovn concerto")
        index = index_for([("/synthetic/2.mp3", 0.93)])
        monkeypatch.setattr(library_data_module, "semantic_recall_enabled", lambda: False)
        search = LibraryDataSearch(title="beethoven")
        search.results = [literal]

        LibraryData._add_semantic_results(search, [literal, missed])

        assert search.results == [literal]
        assert index.queried == []

    def test_asking_whether_a_track_is_in_the_library_stays_literal(self):
        """is_in_library() reads len(results) as "the library has this". A
        similar-but-different track answering that question would be wrong, so
        the pass is opt-in rather than something every search gets."""
        assert inspect.signature(LibraryData.do_search).parameters["semantic_recall"].default is False


@pytest.mark.unit
class TestWhatComesBack:
    def test_a_result_already_found_is_not_added_twice(self, index_for):
        literal = _track("/synthetic/1.mp3", searchable_title="beethoven sonata")
        index_for([("/synthetic/1.mp3", 0.99)])
        search = LibraryDataSearch(title="beethoven")
        search.results = [literal]

        LibraryData._add_semantic_results(search, [literal])

        assert search.results == [literal]

    def test_a_negative_term_is_applied_to_what_comes_back(self, index_for):
        """The similarity comparison cannot express "must not contain", so an
        excluded term would otherwise return through this path."""
        literal = _track("/synthetic/1.mp3", searchable_title="beethoven sonata")
        excluded = _track("/synthetic/2.mp3", searchable_title="beethovn requiem")
        wanted = _track("/synthetic/3.mp3", searchable_title="beethovn concerto")
        index_for([("/synthetic/2.mp3", 0.95), ("/synthetic/3.mp3", 0.93)])
        search = LibraryDataSearch(title="beethoven, -requiem")
        search.results = [literal]

        LibraryData._add_semantic_results(search, [literal, excluded, wanted])

        assert search.results == [literal, wanted]

    def test_a_match_for_a_track_no_longer_in_the_library_is_skipped(self, index_for):
        """The index can name a filepath the current scan no longer has."""
        literal = _track("/synthetic/1.mp3", searchable_title="beethoven sonata")
        index_for([("/synthetic/gone.mp3", 0.95)])
        search = LibraryDataSearch(title="beethoven")
        search.results = [literal]

        LibraryData._add_semantic_results(search, [literal])

        assert search.results == [literal]

    def test_a_failing_index_leaves_the_literal_results(self, monkeypatch, index_for):
        literal = _track("/synthetic/1.mp3", searchable_title="beethoven sonata")
        index_for([])

        class _Raises:
            def ensure_built(self, *args, **kwargs):
                raise RuntimeError("the store is unavailable")

        monkeypatch.setattr(library_data_module, "get_store", lambda: _Raises())
        search = LibraryDataSearch(title="beethoven")
        search.results = [literal]

        LibraryData._add_semantic_results(search, [literal])

        assert search.results == [literal]


@pytest.mark.unit
class TestWhereTheyLand:
    """Recalled tracks are mixed into the one list rather than shown apart. They
    settle below the literal hits on their own: nothing in them matches the query
    as a substring, so _match_relevance() puts every one in tier 2.
    """

    @staticmethod
    def _searched(index_for):
        literal_prefix = _track("/synthetic/1.mp3", searchable_title="beethoven sonata")
        literal_boundary = _track("/synthetic/2.mp3", searchable_title="piano: beethoven")
        missed = _track("/synthetic/3.mp3", searchable_title="beethovn concerto")
        index_for([("/synthetic/3.mp3", 0.93)])
        search = LibraryDataSearch(title="beethoven")
        search.results = [literal_prefix, literal_boundary]
        LibraryData._add_semantic_results(search, [literal_prefix, literal_boundary, missed])
        return search, literal_prefix, literal_boundary, missed

    def test_a_recalled_track_sorts_below_every_literal_hit(self, index_for):
        search, prefix, boundary, missed = self._searched(index_for)

        search.sort_results_by()

        assert search.results == [prefix, boundary, missed]

    def test_the_ranking_signal_does_not_lift_it_past_them(self, monkeypatch, index_for):
        """Even scoring the recalled track as a perfect match and the literal
        ones as unrelated, tier 2 cannot overtake tier 0 or tier 1."""
        search, prefix, boundary, missed = self._searched(index_for)
        monkeypatch.setattr(config, "search_enable_embedding_ranking", True, raising=False)
        monkeypatch.setattr("muse.track_affinity.embed_texts", lambda texts: [
            {"title: beethoven": [1.0, 0.0],
             "title: beethoven sonata": [0.0, 1.0],
             "title: piano: beethoven": [0.0, 1.0],
             "title: beethovn concerto": [1.0, 0.0]}[text] for text in texts])
        assert search.compute_embedding_scores() is True

        search.sort_results_by()

        assert search.results == [prefix, boundary, missed]
