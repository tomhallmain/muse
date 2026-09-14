"""Unit tests for the embedding signal blended into LibraryDataSearch ordering.

Vectors are supplied directly rather than computed, so what is under test is the
blend arithmetic, the binding of scores to what they were computed from, and the
decline paths -- not the model. The stub replaces ``embed_texts`` in
``muse.track_affinity``, which is the seam the caller reads: the import inside
compute_embedding_scores() is deferred, so it picks up the patched attribute.
Supplying the vectors as a mapping from text also pins which texts get embedded,
which a positional list would leave unchecked.

User data isolation: every track here is an in-memory stub and nothing under test
reads the filesystem, the library or the cache -- filepaths below are synthetic
strings used as score keys and as a tie-break. Importing the module pulls in the
config and cache singletons, which tests/bootstrap_env.py has already redirected
to a temporary directory.
"""

from types import SimpleNamespace

import pytest

from library_data.library_data import SEARCH_EMBEDDING_WEIGHT, LibraryDataSearch
from utils.config import config

# Two dimensions place a vector at any similarity to the query.
QUERY_VECTOR = [1.0, 0.0]
SAME = [1.0, 0.0]        # similarity 1.0
HALFWAY = [1.0, 1.0]     # similarity ~0.707
UNRELATED = [0.0, 1.0]   # similarity 0.0


def _track(filepath="/synthetic/track.mp3", **overrides):
    defaults = dict(
        filepath=filepath,
        searchable_title="", searchable_artist="", searchable_composer="",
        searchable_album="", searchable_genre="",
        get_instrument=lambda: "", get_form=lambda: "", get_catalogue=lambda: "",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _vectors_for(monkeypatch, by_text):
    """Stand in for the model. Unexpected text raises, pinning what is embedded."""

    def fake_embed_texts(texts):
        return [by_text[text] for text in texts]

    monkeypatch.setattr("muse.track_affinity.embed_texts", fake_embed_texts)


def _unreachable_model(monkeypatch, why):
    def fail(texts):
        raise AssertionError(f"the model must not be reached {why}")

    monkeypatch.setattr("muse.track_affinity.embed_texts", fail)


@pytest.fixture(autouse=True)
def feature_on(monkeypatch):
    monkeypatch.setattr(config, "search_enable_embedding_ranking", True, raising=False)


@pytest.mark.unit
class TestWeight:
    def test_the_embedding_cannot_outweigh_a_tier_step(self):
        """Normalised, a tier step is worth 0.5 * (1 - weight) and the embedding
        can move a result by at most the weight, so anything from 1/3 up would
        let a tier-2 hit overtake a tier-0 one."""
        assert SEARCH_EMBEDDING_WEIGHT < 1.0 / 3.0


@pytest.mark.unit
class TestBlendedOrdering:
    def test_a_prefix_hit_stays_ahead_of_a_weaker_tier_with_a_better_score(self, monkeypatch):
        prefix = _track(searchable_title="beethoven sonata", filepath="/synthetic/1.mp3")
        boundary = _track(searchable_title="piano: beethoven", filepath="/synthetic/2.mp3")
        inside = _track(searchable_title="xbeethoven works", filepath="/synthetic/3.mp3")
        search = LibraryDataSearch(title="beethoven")
        search.results = [boundary, inside, prefix]
        _vectors_for(monkeypatch, {
            "title: beethoven": QUERY_VECTOR,
            "title: beethoven sonata": UNRELATED,
            "title: piano: beethoven": SAME,
            "title: xbeethoven works": SAME,
        })
        assert search.compute_embedding_scores() is True

        search.sort_results_by()

        assert search.results == [prefix, boundary, inside]

    def test_a_closer_result_leads_its_tier(self, monkeypatch):
        """Within a tier the embedding decides the order, with the value string
        left as the tie-break behind it."""
        far = _track(searchable_title="beethoven a", filepath="/synthetic/1.mp3")
        near = _track(searchable_title="beethoven b", filepath="/synthetic/2.mp3")
        middle = _track(searchable_title="beethoven c", filepath="/synthetic/3.mp3")
        search = LibraryDataSearch(title="beethoven")
        search.results = [far, near, middle]
        _vectors_for(monkeypatch, {
            "title: beethoven": QUERY_VECTOR,
            "title: beethoven a": UNRELATED,
            "title: beethoven b": SAME,
            "title: beethoven c": HALFWAY,
        })
        assert search.compute_embedding_scores() is True

        search.sort_results_by()

        assert search.results == [near, middle, far]

    def test_a_getter_field_is_scored_the_same_way(self, monkeypatch):
        """instrument, form and catalogue resolve to getters rather than fields."""
        near = _track(get_catalogue=lambda: "bwv 1046", filepath="/synthetic/1.mp3")
        far = _track(get_catalogue=lambda: "bwv 1047", filepath="/synthetic/2.mp3")
        search = LibraryDataSearch(catalogue="bwv")
        search.results = [far, near]
        _vectors_for(monkeypatch, {
            "catalogue: bwv": QUERY_VECTOR,
            "catalogue: bwv 1046": SAME,
            "catalogue: bwv 1047": UNRELATED,
        })
        assert search.compute_embedding_scores() is True

        search.sort_results_by()

        assert search.results == [near, far]


@pytest.mark.unit
class TestEqualValuesStayGrouped:
    """What keeps an album together under the blend: tracks sharing a field value
    embed identical text, so they take an identical score and the value-then-
    filepath tie-break still decides among them. A track tagged differently takes
    its own score and orders apart from them.

    That rests on identical text giving an identical vector, which holds because
    the same text is one row of the same forward pass, and because the
    searchable_* values are lowercased and ascii-normalised before they get here.
    """

    def test_one_artist_across_an_album_keeps_the_album_in_track_order(self, monkeypatch):
        third = _track(searchable_artist="duke ellington", filepath="/album/03.mp3")
        first = _track(searchable_artist="duke ellington", filepath="/album/01.mp3")
        second = _track(searchable_artist="duke ellington", filepath="/album/02.mp3")
        search = LibraryDataSearch(artist="duke ellington")
        search.results = [third, first, second]
        _vectors_for(monkeypatch, {"artist: duke ellington": QUERY_VECTOR})
        assert search.compute_embedding_scores() is True
        assert len(set(search._embedding_ranking.scores.values())) == 1

        search.sort_results_by()

        assert search.results == [first, second, third]

    def test_a_differently_tagged_track_is_ranked_on_its_own(self, monkeypatch):
        """A co-credited track on an otherwise single-artist album carries its own
        value, so it is scored separately and moves, while the tracks that share a
        value stay contiguous and in track order."""
        first = _track(searchable_artist="duke ellington orchestra", filepath="/album/01.mp3")
        second = _track(searchable_artist="duke ellington orchestra", filepath="/album/02.mp3")
        co_credited = _track(searchable_artist="billy strayhorn & duke ellington",
                             filepath="/album/03.mp3")
        fourth = _track(searchable_artist="duke ellington orchestra", filepath="/album/04.mp3")
        search = LibraryDataSearch(artist="ellington")
        search.results = [first, second, co_credited, fourth]
        # All four are word-boundary hits, so the move below is the embedding
        # reordering within a tier, not the tier hierarchy asserting itself.
        assert {LibraryDataSearch._match_relevance(track.searchable_artist, "ellington")
                for track in search.results} == {1}
        _vectors_for(monkeypatch, {
            "artist: ellington": QUERY_VECTOR,
            "artist: duke ellington orchestra": SAME,
            "artist: billy strayhorn & duke ellington": UNRELATED,
        })
        assert search.compute_embedding_scores() is True

        search.sort_results_by()

        assert search.results == [first, second, fourth, co_credited]


@pytest.mark.unit
class TestAllFieldOrdering:
    def test_an_all_search_is_ordered_by_similarity(self, monkeypatch):
        """The "all" field has no track value of its own, so the several fields
        it searched are what each result is compared by."""
        near = _track(searchable_title="moonlight sonata",
                      searchable_composer="beethoven", filepath="/synthetic/1.mp3")
        far = _track(searchable_title="jupiter symphony",
                     searchable_composer="mozart", filepath="/synthetic/2.mp3")
        search = LibraryDataSearch(all="beethoven")
        search.results = [far, near]
        _vectors_for(monkeypatch, {
            "beethoven": QUERY_VECTOR,
            "moonlight sonata, beethoven": SAME,
            "jupiter symphony, mozart": UNRELATED,
        })
        assert search.compute_embedding_scores() is True

        search.sort_results_by()

        assert search.results == [near, far]

    def test_an_all_search_keeps_scan_order_without_scores(self):
        """With no usable score there is no field to fall back to, so the order
        the library was scanned in stands."""
        first = _track(searchable_title="zzz", filepath="/synthetic/z.mp3")
        second = _track(searchable_title="beethoven", filepath="/synthetic/a.mp3")
        search = LibraryDataSearch(all="beethoven")
        search.results = [first, second]

        search.sort_results_by()

        assert search.results == [first, second]

    def test_a_named_field_wins_the_derivation_over_all(self, monkeypatch):
        search = LibraryDataSearch(all="mozart", title="beethoven")
        search.results = [_track(searchable_title="beethoven", filepath="/synthetic/1.mp3")]
        _vectors_for(monkeypatch, {"title: beethoven": QUERY_VECTOR})

        assert search.compute_embedding_scores() is True

        assert search._embedding_ranking.field == "title"

    def test_a_track_with_nothing_to_compare_scores_zero(self, monkeypatch):
        """It is still recorded, so the scores cover the whole result set and
        stay usable for the results that do have text."""
        empty = _track(filepath="/synthetic/1.mp3")
        named = _track(searchable_title="beethoven sonata", filepath="/synthetic/2.mp3")
        search = LibraryDataSearch(all="beethoven")
        search.results = [empty, named]
        _vectors_for(monkeypatch, {
            "beethoven": QUERY_VECTOR,
            "beethoven sonata": SAME,
        })
        assert search.compute_embedding_scores() is True

        assert search._embedding_ranking.scores["/synthetic/1.mp3"] == 0.0
        search.sort_results_by()
        assert search.results == [named, empty]


@pytest.mark.unit
class TestScoresAreBoundToWhatTheyCameFrom:
    """Every case here is arranged so that the scores, if applied, give a
    different order from the lexical one -- otherwise a fallback that silently
    failed to happen would still pass."""

    @staticmethod
    def _scored_search(monkeypatch):
        alpha = _track(searchable_title="beethoven alpha", searchable_album="a first",
                       filepath="/synthetic/1.mp3")
        zulu = _track(searchable_title="beethoven zulu", searchable_album="a second",
                      filepath="/synthetic/2.mp3")
        search = LibraryDataSearch(title="beethoven", album="a")
        search.results = [alpha, zulu]
        _vectors_for(monkeypatch, {
            "title: beethoven": QUERY_VECTOR,
            "title: beethoven alpha": UNRELATED,
            "title: beethoven zulu": SAME,
        })
        assert search.compute_embedding_scores() is True
        return search, alpha, zulu

    def test_the_field_the_scores_came_from_keeps_using_them(self, monkeypatch):
        search, alpha, zulu = self._scored_search(monkeypatch)

        search.sort_results_by(attr="title")

        assert search.results == [zulu, alpha]

    def test_a_column_switch_falls_back_to_the_lexical_order(self, monkeypatch):
        """Both albums are tier 0 here, so a title score applied to an album sort
        would show -- it would put the second album first."""
        search, alpha, zulu = self._scored_search(monkeypatch)

        search.sort_results_by(attr="album")

        assert search.results == [alpha, zulu]

    def test_a_further_page_of_results_falls_back_to_the_lexical_order(self, monkeypatch):
        """"Load more" merges in tracks the scores say nothing about."""
        search, alpha, zulu = self._scored_search(monkeypatch)
        unscored = _track(searchable_title="beethoven mid", filepath="/synthetic/3.mp3")
        search.results.append(unscored)

        search.sort_results_by()

        assert search.results == [alpha, unscored, zulu]

    def test_an_edited_query_falls_back_to_the_lexical_order(self, monkeypatch):
        search, alpha, zulu = self._scored_search(monkeypatch)
        search.title = "mozart"
        search._field_terms["title"] = LibraryDataSearch._parse_terms("mozart")

        search.sort_results_by()

        assert search.results == [alpha, zulu]


@pytest.mark.unit
class TestQueryText:
    def test_a_named_field_is_labelled(self):
        search = LibraryDataSearch(composer="beethoven")
        assert search._embedding_query_text("composer") == "composer: beethoven"

    def test_the_all_field_is_not_labelled(self):
        search = LibraryDataSearch(all="beethoven")
        assert search._embedding_query_text("all") == "beethoven"

    def test_only_positive_terms_are_embedded(self):
        """Negative terms already excluded their tracks, so they cannot affect
        ordering within the result set."""
        search = LibraryDataSearch(title="beethoven, -sonata")
        assert search._embedding_query_text("title") == "title: beethoven"

    def test_an_empty_field_has_nothing_to_embed(self):
        search = LibraryDataSearch(title="beethoven")
        assert search._embedding_query_text("album") == ""


@pytest.mark.unit
class TestDeclinePaths:
    """Each of these leaves the scores unset, which is what the sort reads as
    "order lexically", so none of them can change what the window shows."""

    @staticmethod
    def _search():
        search = LibraryDataSearch(title="beethoven")
        search.results = [_track(searchable_title="beethoven")]
        return search

    def test_the_config_flag_turns_the_pass_off(self, monkeypatch):
        monkeypatch.setattr(config, "search_enable_embedding_ranking", False, raising=False)
        _unreachable_model(monkeypatch, "when the flag is off")
        search = self._search()

        assert search.compute_embedding_scores() is False
        assert search._embedding_ranking is None

    def test_a_missing_model_leaves_the_lexical_order(self, monkeypatch):
        """embed_texts() answers None where sentence-transformers is absent."""
        monkeypatch.setattr("muse.track_affinity.embed_texts", lambda texts: None)
        search = self._search()

        assert search.compute_embedding_scores() is False
        assert search._embedding_ranking is None

    def test_a_raising_model_is_contained(self, monkeypatch):
        def _raise(texts):
            raise RuntimeError("no model")

        monkeypatch.setattr("muse.track_affinity.embed_texts", _raise)
        search = self._search()

        assert search.compute_embedding_scores() is False
        assert search._embedding_ranking is None

    def test_a_short_answer_is_rejected(self, monkeypatch):
        """One vector back for a query and a result is not a usable answer."""
        monkeypatch.setattr("muse.track_affinity.embed_texts", lambda texts: [QUERY_VECTOR])
        search = self._search()

        assert search.compute_embedding_scores() is False
        assert search._embedding_ranking is None

    def test_an_incomparable_vector_is_rejected(self, monkeypatch):
        monkeypatch.setattr("muse.track_affinity.embed_texts",
                            lambda texts: [QUERY_VECTOR, [0.0, 0.0]])
        search = self._search()

        assert search.compute_embedding_scores() is False
        assert search._embedding_ranking is None

    def test_an_empty_result_set_has_nothing_to_score(self, monkeypatch):
        _unreachable_model(monkeypatch, "with no results")
        search = LibraryDataSearch(title="beethoven")

        assert search.compute_embedding_scores() is False

    def test_a_search_with_no_field_at_all_is_skipped(self, monkeypatch):
        _unreachable_model(monkeypatch, "with no field to compare")
        search = LibraryDataSearch()
        search.results = [_track()]

        assert search.compute_embedding_scores() is False
        assert search._embedding_ranking is None

    def test_an_unknown_explicit_attribute_is_contained(self, monkeypatch):
        """sort_results_by() raises on one; the scoring pass only declines."""
        _unreachable_model(monkeypatch, "for an attribute that cannot be resolved")
        search = self._search()

        assert search.compute_embedding_scores(attr="all") is False
        assert search._embedding_ranking is None


@pytest.mark.unit
class TestSearchIdentity:
    def test_scores_do_not_affect_equality_or_hashing(self, monkeypatch):
        """Recent searches are deduplicated by value and held in a set, so a
        scored search and an unscored one must still be the same search."""
        scored = LibraryDataSearch(title="beethoven")
        scored.results = [_track(searchable_title="beethoven")]
        _vectors_for(monkeypatch, {"title: beethoven": QUERY_VECTOR})
        assert scored.compute_embedding_scores() is True
        plain = LibraryDataSearch(title="beethoven")

        assert scored == plain
        assert hash(scored) == hash(plain)
        assert scored.matches_no_selected_track_path(plain)
