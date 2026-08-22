"""Unit tests for affinity ordering of the upcoming window in muse/playlist.py.

The tracks are assigned to ``sorted_tracks`` directly rather than sorted into
place, so that the group layout each case needs is exact and the assertions are
about the reordering alone.
"""

import pytest

from muse import Playlist
from muse.track_affinity import DEFAULT_AFFINITY_WINDOW, AffinityReference
from tests.conftest import MockMediaTrack
from utils.globals import PlaylistSortType


def _track(index, composer):
    return MockMediaTrack(
        filepath=f"track_{index}.mp3",
        title=f"Track {index}",
        album=f"{composer} Album",
        artist="Some Performer",
        composer=composer,
        _genre="Classical",
        _form="Symphony",
        _instrument="Orchestra",
        _catalogue="",
    )


def _playlist(mock_data_callbacks, tracks, reference=None,
              sort_type=PlaylistSortType.COMPOSER_SHUFFLE):
    # Built empty and filled afterwards: an empty playlist skips sort(), so the
    # group layout each case needs survives exactly as written.
    playlist = Playlist([], _type=sort_type, data_callbacks=mock_data_callbacks,
                        affinity_reference=reference)
    playlist.sorted_tracks = list(tracks)
    return playlist


def _grouped(group_sizes):
    """Tracks laid out in contiguous runs, one composer per run."""
    tracks = []
    for group_index, size in enumerate(group_sizes):
        for _ in range(size):
            tracks.append(_track(len(tracks), f"Composer{group_index}"))
    return tracks


def _composer_of(track):
    return track.composer


def _reference(composer):
    reference = AffinityReference()
    reference.add("composer", composer)
    return reference


@pytest.fixture
def affinity_on(monkeypatch):
    """Enable affinity in "similar" mode without touching the user's config."""
    monkeypatch.setattr("muse.playlist.affinity_enabled", lambda: True)
    monkeypatch.setattr("muse.playlist.affinity_prefers_similar", lambda: True)


@pytest.fixture
def affinity_varied(monkeypatch):
    monkeypatch.setattr("muse.playlist.affinity_enabled", lambda: True)
    monkeypatch.setattr("muse.playlist.affinity_prefers_similar", lambda: False)


@pytest.mark.unit
class TestAffinityWindowEnd:
    def test_short_playlist_is_entirely_in_the_window(self, mock_data_callbacks):
        playlist = _playlist(mock_data_callbacks, _grouped([3, 3]))

        assert playlist._affinity_window_end(_composer_of) == 6

    def test_window_extends_to_finish_the_group_it_lands_in(self, mock_data_callbacks):
        # Groups of 6: index 39 (the last in the window) falls inside the group
        # spanning 36..41, so the window should take in all of it.
        playlist = _playlist(mock_data_callbacks, _grouped([6] * 20))

        assert playlist._affinity_window_end(_composer_of) == 42

    def test_window_ending_on_a_boundary_is_not_extended(self, mock_data_callbacks):
        # Groups of 10 put a boundary exactly at index 40.
        playlist = _playlist(mock_data_callbacks, _grouped([10] * 10))

        assert playlist._affinity_window_end(_composer_of) == DEFAULT_AFFINITY_WINDOW

    def test_group_larger_than_the_window_is_cut(self, mock_data_callbacks):
        """A group longer than the window has no coherent run worth preserving,
        so extending would swallow the whole playlist for nothing."""
        playlist = _playlist(mock_data_callbacks, _grouped([30, 100]))

        assert playlist._affinity_window_end(_composer_of) == DEFAULT_AFFINITY_WINDOW


@pytest.mark.unit
class TestApplyAffinityOrdering:
    def test_no_reference_means_no_reordering(self, mock_data_callbacks, affinity_on):
        playlist = _playlist(mock_data_callbacks, _grouped([2, 2]))
        before = list(playlist.sorted_tracks)

        assert playlist.apply_affinity_ordering(_composer_of) is False
        assert playlist.sorted_tracks == before

    def test_empty_reference_means_no_reordering(self, mock_data_callbacks, affinity_on):
        playlist = _playlist(mock_data_callbacks, _grouped([2, 2]), AffinityReference())

        assert playlist.apply_affinity_ordering(_composer_of) is False

    def test_disabled_preference_means_no_reordering(self, mock_data_callbacks, monkeypatch):
        monkeypatch.setattr("muse.playlist.affinity_enabled", lambda: False)
        playlist = _playlist(mock_data_callbacks, _grouped([2, 2]), _reference("Composer1"))
        before = list(playlist.sorted_tracks)

        assert playlist.apply_affinity_ordering(_composer_of) is False
        assert playlist.sorted_tracks == before

    def test_single_group_means_no_reordering(self, mock_data_callbacks, affinity_on):
        playlist = _playlist(mock_data_callbacks, _grouped([4]), _reference("Composer0"))

        assert playlist.apply_affinity_ordering(_composer_of) is False

    def test_similar_pulls_the_matching_group_forward(self, mock_data_callbacks, affinity_on):
        playlist = _playlist(mock_data_callbacks, _grouped([2, 2, 2]), _reference("Composer2"))

        assert playlist.apply_affinity_ordering(_composer_of) is True
        assert [t.composer for t in playlist.sorted_tracks] == [
            "Composer2", "Composer2", "Composer0", "Composer0", "Composer1", "Composer1"]

    def test_varied_pushes_the_matching_group_back(self, mock_data_callbacks, affinity_varied):
        playlist = _playlist(mock_data_callbacks, _grouped([2, 2, 2]), _reference("Composer0"))

        assert playlist.apply_affinity_ordering(_composer_of) is True
        assert [t.composer for t in playlist.sorted_tracks] == [
            "Composer1", "Composer1", "Composer2", "Composer2", "Composer0", "Composer0"]

    def test_groups_move_as_whole_units(self, mock_data_callbacks, affinity_on):
        """The grouping sort made each run contiguous; scoring must not break it."""
        playlist = _playlist(mock_data_callbacks, _grouped([3, 1, 4]), _reference("Composer2"))
        playlist.apply_affinity_ordering(_composer_of)

        composers = [t.composer for t in playlist.sorted_tracks]
        runs = [c for i, c in enumerate(composers) if i == 0 or composers[i - 1] != c]
        assert len(runs) == len(set(runs))

    def test_equal_scoring_groups_keep_their_original_order(self, mock_data_callbacks, affinity_on):
        """Nothing here matches, so the grouping sort's order should survive intact."""
        playlist = _playlist(mock_data_callbacks, _grouped([2, 2, 2]), _reference("Nobody"))
        before = list(playlist.sorted_tracks)

        playlist.apply_affinity_ordering(_composer_of)

        assert playlist.sorted_tracks == before

    def test_tracks_beyond_the_window_are_untouched(self, mock_data_callbacks, affinity_on):
        # Groups of 10: the window ends on the boundary at index 40, leaving the
        # last two groups where they were.
        playlist = _playlist(mock_data_callbacks, _grouped([10] * 6), _reference("Composer3"))
        tail = list(playlist.sorted_tracks[40:])

        playlist.apply_affinity_ordering(_composer_of)

        assert playlist.sorted_tracks[40:] == tail
        assert [t.composer for t in playlist.sorted_tracks[:10]] == ["Composer3"] * 10

    def test_no_tracks_are_lost_or_duplicated(self, mock_data_callbacks, affinity_on):
        playlist = _playlist(mock_data_callbacks, _grouped([3, 5, 2, 7]), _reference("Composer2"))
        before = list(playlist.sorted_tracks)

        playlist.apply_affinity_ordering(_composer_of)

        assert sorted(t.filepath for t in playlist.sorted_tracks) == \
            sorted(t.filepath for t in before)

    def test_group_scores_by_its_best_track(self, mock_data_callbacks, affinity_on):
        """One matching track is enough to bring its whole group forward."""
        tracks = _grouped([2, 2])
        tracks[3]._form = "Concerto"
        reference = AffinityReference()
        reference.add("form", "Concerto")
        playlist = _playlist(mock_data_callbacks, tracks, reference)

        assert playlist.apply_affinity_ordering(_composer_of) is True
        assert [t.composer for t in playlist.sorted_tracks[:2]] == ["Composer1"] * 2


@pytest.mark.unit
class TestAffinityOrderingFromAnOffset:
    def test_tracks_before_the_start_are_never_moved(self, mock_data_callbacks, affinity_on):
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 6), _reference("Composer5"))
        head = list(playlist.sorted_tracks[:4])

        assert playlist.apply_affinity_ordering(_composer_of, start=4) is True
        assert playlist.sorted_tracks[:4] == head
        assert [t.composer for t in playlist.sorted_tracks[4:6]] == ["Composer5"] * 2

    def test_the_window_is_measured_from_the_start(self, mock_data_callbacks):
        # Groups of 10 from offset 5: the window covers 5..45, which falls inside
        # the group spanning 40..49, so it extends to 50.
        playlist = _playlist(mock_data_callbacks, _grouped([10] * 10))

        assert playlist._affinity_window_end(_composer_of, start=5) == 50

    def test_too_little_left_to_reorder(self, mock_data_callbacks, affinity_on):
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 6), _reference("Composer5"))

        assert playlist.apply_affinity_ordering(_composer_of, start=11) is False

    def test_a_negative_start_is_treated_as_the_beginning(self, mock_data_callbacks, affinity_on):
        """current_track_index is -1 before the first track, so start comes through
        as 0."""
        playlist = _playlist(mock_data_callbacks, _grouped([2, 2]), _reference("Composer1"))

        assert playlist.apply_affinity_ordering(_composer_of, start=-1) is True
        assert [t.composer for t in playlist.sorted_tracks[:2]] == ["Composer1"] * 2


@pytest.mark.unit
class TestResortUpcoming:
    def test_reorders_only_what_has_not_been_played(self, mock_data_callbacks, affinity_on):
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 6), _reference("Composer5"))
        playlist.current_track_index = 3
        played = list(playlist.sorted_tracks[:4])

        assert playlist.resort_upcoming() is True
        assert playlist.sorted_tracks[:4] == played
        assert [t.composer for t in playlist.sorted_tracks[4:6]] == ["Composer5"] * 2

    def test_before_the_first_track_the_whole_playlist_is_open(self, mock_data_callbacks, affinity_on):
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 3), _reference("Composer2"))

        assert playlist.resort_upcoming() is True
        assert [t.composer for t in playlist.sorted_tracks[:2]] == ["Composer2"] * 2

    @pytest.mark.parametrize("sort_type", [PlaylistSortType.SEQUENCE, PlaylistSortType.RANDOM])
    def test_ungrouped_sorts_have_nothing_to_resort(self, mock_data_callbacks, affinity_on, sort_type):
        """Neither sort groups tracks, so there are no group units to move."""
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 6), _reference("Composer5"),
                             sort_type=sort_type)
        before = list(playlist.sorted_tracks)

        assert playlist.resort_upcoming() is False
        assert playlist.sorted_tracks == before

    def test_nothing_left_to_play(self, mock_data_callbacks, affinity_on):
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 6), _reference("Composer5"))
        playlist.current_track_index = len(playlist.sorted_tracks) - 1

        assert playlist.resort_upcoming() is False

    def test_no_reference_leaves_playback_order_alone(self, mock_data_callbacks, affinity_on):
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 6))
        playlist.current_track_index = 3
        before = list(playlist.sorted_tracks)

        assert playlist.resort_upcoming() is False
        assert playlist.sorted_tracks == before


@pytest.mark.unit
class TestUpcomingGroupValues:
    def test_each_group_is_listed_once_in_playing_order(self, mock_data_callbacks):
        playlist = _playlist(mock_data_callbacks, _grouped([2, 3, 1]))

        assert playlist.upcoming_group_values() == ["Composer0", "Composer1", "Composer2"]

    def test_played_groups_are_excluded(self, mock_data_callbacks):
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 4))
        playlist.current_track_index = 3

        assert playlist.upcoming_group_values() == ["Composer2", "Composer3"]

    def test_only_groups_inside_the_window_are_listed(self, mock_data_callbacks):
        # Groups of 10: the window ends on the boundary at 40, so the last two
        # groups are past it.
        playlist = _playlist(mock_data_callbacks, _grouped([10] * 6))

        assert playlist.upcoming_group_values() == [f"Composer{i}" for i in range(4)]

    def test_ungrouped_sorts_have_no_group_values(self, mock_data_callbacks):
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 3),
                             sort_type=PlaylistSortType.SEQUENCE)

        assert playlist.upcoming_group_values() == []

    def test_nothing_left_to_play(self, mock_data_callbacks):
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 3))
        playlist.current_track_index = len(playlist.sorted_tracks) - 1

        assert playlist.upcoming_group_values() == []


@pytest.mark.unit
class TestRefreshLlmGroupScores:
    def test_learned_scores_are_kept(self, mock_data_callbacks, affinity_on, monkeypatch):
        monkeypatch.setattr("muse.playlist.llm_group_scores",
                            lambda reference, values: {v: 0.5 for v in values})
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 3), _reference("Composer0"))

        assert playlist.refresh_llm_group_scores() is True
        assert playlist.llm_affinity_scores == {f"Composer{i}": 0.5 for i in range(3)}

    def test_only_unscored_groups_are_asked_about(self, mock_data_callbacks, affinity_on, monkeypatch):
        """A long session should not re-pay for judgements it already has."""
        asked = []

        def _scores(_reference_arg, values):
            asked.append(list(values))
            return {v: 0.5 for v in values}

        monkeypatch.setattr("muse.playlist.llm_group_scores", _scores)
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 3), _reference("Composer0"))
        playlist.llm_affinity_scores["Composer0"] = 0.9

        playlist.refresh_llm_group_scores()

        assert asked == [["Composer1", "Composer2"]]
        assert playlist.llm_affinity_scores["Composer0"] == 0.9

    def test_nothing_new_to_ask_makes_no_call(self, mock_data_callbacks, affinity_on, monkeypatch):
        def _fail(*_a, **_k):
            raise AssertionError("should not have been called")

        monkeypatch.setattr("muse.playlist.llm_group_scores", _fail)
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 2), _reference("Composer0"))
        playlist.llm_affinity_scores.update({"Composer0": 0.1, "Composer1": 0.2})

        assert playlist.refresh_llm_group_scores() is False

    def test_a_declined_answer_changes_nothing(self, mock_data_callbacks, affinity_on, monkeypatch):
        monkeypatch.setattr("muse.playlist.llm_group_scores", lambda *_a: None)
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 3), _reference("Composer0"))

        assert playlist.refresh_llm_group_scores() is False
        assert playlist.llm_affinity_scores == {}

    def test_no_reference_means_no_call(self, mock_data_callbacks, affinity_on, monkeypatch):
        def _fail(*_a, **_k):
            raise AssertionError("should not have been called")

        monkeypatch.setattr("muse.playlist.llm_group_scores", _fail)
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 3))

        assert playlist.refresh_llm_group_scores() is False

    def test_disabled_preference_means_no_call(self, mock_data_callbacks, monkeypatch):
        monkeypatch.setattr("muse.playlist.affinity_enabled", lambda: False)

        def _fail(*_a, **_k):
            raise AssertionError("should not have been called")

        monkeypatch.setattr("muse.playlist.llm_group_scores", _fail)
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 3), _reference("Composer0"))

        assert playlist.refresh_llm_group_scores() is False


@pytest.mark.unit
class TestGroupAttributeName:
    @pytest.mark.parametrize("sort_type,expected", [
        (PlaylistSortType.COMPOSER_SHUFFLE, "composer"),
        (PlaylistSortType.ALBUM_SHUFFLE, "album"),
        (PlaylistSortType.GENRE_SHUFFLE, "genre"),
        (PlaylistSortType.INSTRUMENT_SHUFFLE, "instrument"),
    ])
    def test_the_getter_prefix_is_stripped(self, mock_data_callbacks, sort_type, expected):
        playlist = _playlist(mock_data_callbacks, [], sort_type=sort_type)

        assert playlist.group_attribute_name() == expected

    def test_main_artist_reads_as_artist(self, mock_data_callbacks):
        """It is still an artist grouping as far as judging relatedness goes."""
        playlist = _playlist(mock_data_callbacks, [],
                             sort_type=PlaylistSortType.MAIN_ARTIST_SHUFFLE)

        assert playlist.group_attribute_name() == "artist"

    def test_a_sort_with_no_grouping_has_no_attribute(self, mock_data_callbacks):
        playlist = _playlist(mock_data_callbacks, [], sort_type=PlaylistSortType.SEQUENCE)

        assert playlist.group_attribute_name() == ""


@pytest.mark.unit
class TestRefreshEmbeddingGroupScores:
    def test_learned_scores_are_kept_separately(self, mock_data_callbacks, affinity_on, monkeypatch):
        monkeypatch.setattr("muse.playlist.embedding_group_scores",
                            lambda reference, values, attribute="": {v: 0.4 for v in values})
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 2), _reference("Composer0"))

        assert playlist.refresh_embedding_group_scores() is True
        assert playlist.embedding_affinity_scores == {"Composer0": 0.4, "Composer1": 0.4}
        assert playlist.llm_affinity_scores == {}

    def test_the_grouping_attribute_is_passed_through(self, mock_data_callbacks, affinity_on, monkeypatch):
        seen = {}

        def _scores(_reference_arg, values, attribute=""):
            seen["attribute"] = attribute
            return {v: 0.4 for v in values}

        monkeypatch.setattr("muse.playlist.embedding_group_scores", _scores)
        playlist = _playlist(mock_data_callbacks, _grouped([2]), _reference("Composer0"))
        playlist.refresh_embedding_group_scores()

        assert seen["attribute"] == "composer"

    def test_a_declined_answer_changes_nothing(self, mock_data_callbacks, affinity_on, monkeypatch):
        monkeypatch.setattr("muse.playlist.embedding_group_scores", lambda *_a, **_k: None)
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 2), _reference("Composer0"))

        assert playlist.refresh_embedding_group_scores() is False
        assert playlist.embedding_affinity_scores == {}

    def test_only_unscored_groups_are_asked_about(self, mock_data_callbacks, affinity_on, monkeypatch):
        asked = []

        def _scores(_reference_arg, values, attribute=""):
            asked.append(list(values))
            return {v: 0.4 for v in values}

        monkeypatch.setattr("muse.playlist.embedding_group_scores", _scores)
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 3), _reference("Composer0"))
        playlist.embedding_affinity_scores["Composer0"] = 0.9

        playlist.refresh_embedding_group_scores()

        assert asked == [["Composer1", "Composer2"]]


@pytest.mark.unit
class TestOrderingWithModelScores:
    def test_a_model_score_can_promote_an_unrelated_group(self, mock_data_callbacks, affinity_on):
        """The reason this tier exists: attribute overlap rates Composer2 at zero,
        and only the model can say it belongs near Composer0."""
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 3), _reference("Composer0"))
        playlist.llm_affinity_scores["Composer2"] = 1.0

        playlist.apply_affinity_ordering(_composer_of)

        assert [t.composer for t in playlist.sorted_tracks[:2]] == ["Composer0"] * 2
        assert [t.composer for t in playlist.sorted_tracks[2:4]] == ["Composer2"] * 2

    def test_the_model_cannot_override_an_exact_attribute_match(self, mock_data_callbacks, affinity_on):
        """Blended, not replaced: a zero from the model still leaves the group the
        tags confirm ahead of one they say nothing about."""
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 2), _reference("Composer1"))
        playlist.llm_affinity_scores.update({"Composer1": 0.0, "Composer0": 0.0})

        playlist.apply_affinity_ordering(_composer_of)

        assert [t.composer for t in playlist.sorted_tracks[:2]] == ["Composer1"] * 2

    def test_no_model_scores_orders_by_attributes_alone(self, mock_data_callbacks, affinity_on):
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 3), _reference("Composer2"))

        assert playlist.apply_affinity_ordering(_composer_of) is True
        assert [t.composer for t in playlist.sorted_tracks[:2]] == ["Composer2"] * 2

    def test_an_embedding_score_can_promote_an_unrelated_group(self, mock_data_callbacks, affinity_on):
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 3), _reference("Composer0"))
        playlist.embedding_affinity_scores["Composer2"] = 1.0

        playlist.apply_affinity_ordering(_composer_of)

        assert [t.composer for t in playlist.sorted_tracks[:2]] == ["Composer0"] * 2
        assert [t.composer for t in playlist.sorted_tracks[2:4]] == ["Composer2"] * 2

    def test_both_signals_agreeing_outweighs_either_alone(self, mock_data_callbacks, affinity_on):
        playlist = _playlist(mock_data_callbacks, _grouped([2] * 3), _reference("Nobody"))
        playlist.llm_affinity_scores["Composer2"] = 1.0
        playlist.embedding_affinity_scores["Composer2"] = 1.0
        playlist.llm_affinity_scores["Composer1"] = 1.0

        playlist.apply_affinity_ordering(_composer_of)

        assert [t.composer for t in playlist.sorted_tracks[:2]] == ["Composer2"] * 2
