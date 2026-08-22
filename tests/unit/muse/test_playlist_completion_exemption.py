"""Tests for cross-sort completion exemption in muse/playlist.py.

One track played marks its album, composer and genre as recently played whatever
grouping was in force, so the next sort demotes a group the listener has barely
started. A group stays eligible until enough of it has actually been heard.
"""

import pytest

from muse import Playlist
from muse.track_affinity import (
    COMPLETION_CAP,
    clear_listening_log,
    record_listening,
    tracks_to_spend,
)
from tests.conftest import MockMediaTrack
from utils.globals import PlaylistSortType


def _track(index, album="An Album", composer="A Composer", seconds=300.0):
    track = MockMediaTrack(
        filepath=f"track_{index}.mp3",
        title=f"Track {index}",
        album=album,
        artist="A Performer",
        composer=composer,
        _genre="Classical",
        _form="Symphony",
        _instrument="Orchestra",
        _catalogue="",
    )
    track.get_track_length = lambda _s=seconds: _s
    return track


class _Library:
    """Stands in for LibraryData, which is the only thing Playlist asks for sizes."""

    def __init__(self, sizes):
        self._sizes = sizes
        self.asked = []

    def get_group_sizes(self, column, values):
        self.asked.append((column, sorted(values)))
        return {v: self._sizes[v] for v in values if v in self._sizes}


def _playlist(mock_data_callbacks, tracks, library=None,
              sort_type=PlaylistSortType.ALBUM_SHUFFLE):
    playlist = Playlist([], _type=sort_type, data_callbacks=mock_data_callbacks)
    playlist.sorted_tracks = list(tracks)
    if library is not None:
        playlist.data_callbacks.instance = library
    return playlist


@pytest.fixture(autouse=True)
def clean_log():
    clear_listening_log()
    yield
    clear_listening_log()


@pytest.mark.unit
class TestTracksToSpend:
    def test_a_single_track_group_spends_in_one(self):
        """Two thirds of composers here have one track; for them the whole group
        genuinely has been played."""
        assert tracks_to_spend(1) == 1

    def test_a_small_group_uses_the_ratio(self):
        assert tracks_to_spend(8) == 2

    def test_a_large_group_is_bounded_by_the_cap(self):
        """Without the cap a 947-track compilation would need 237 plays and could
        never be spent at all."""
        assert tracks_to_spend(947) == COMPLETION_CAP
        assert tracks_to_spend(16550) == COMPLETION_CAP

    def test_the_requirement_never_exceeds_the_cap(self):
        assert all(tracks_to_spend(n) <= COMPLETION_CAP for n in range(1, 200))

    def test_the_requirement_is_never_zero(self):
        assert tracks_to_spend(0) == 1
        assert all(tracks_to_spend(n) >= 1 for n in range(0, 200))


@pytest.mark.unit
class TestCompletionExemptions:
    def test_one_track_does_not_spend_a_long_album(self, mock_data_callbacks):
        library = _Library({"An Album": 15})
        playlist = _playlist(mock_data_callbacks, [], library)
        record_listening(_track(0))

        chance = {}
        playlist._add_completion_exemptions(chance, "album", ["An Album"])

        assert chance == {"an album": 1.0}

    def test_enough_tracks_spend_it(self, mock_data_callbacks):
        """Exactly enough must be enough. The count decays, so it comes back a
        hair under a whole number and a bare comparison would resist for ever."""
        library = _Library({"An Album": 15})
        playlist = _playlist(mock_data_callbacks, [], library)
        for i in range(tracks_to_spend(15)):
            record_listening(_track(i))

        chance = {}
        playlist._add_completion_exemptions(chance, "album", ["An Album"])

        assert chance == {}

    def test_one_short_of_enough_still_resists(self, mock_data_callbacks):
        library = _Library({"An Album": 15})
        playlist = _playlist(mock_data_callbacks, [], library)
        for i in range(tracks_to_spend(15) - 1):
            record_listening(_track(i))

        chance = {}
        playlist._add_completion_exemptions(chance, "album", ["An Album"])

        assert chance == {"an album": 1.0}

    def test_a_single_is_spent_by_its_only_track(self, mock_data_callbacks):
        library = _Library({"A Single": 1})
        playlist = _playlist(mock_data_callbacks, [], library)
        record_listening(_track(0, album="A Single"))

        chance = {}
        playlist._add_completion_exemptions(chance, "album", ["A Single"])

        assert chance == {}

    def test_nothing_played_leaves_the_group_eligible(self, mock_data_callbacks):
        library = _Library({"An Album": 15})
        playlist = _playlist(mock_data_callbacks, [], library)

        chance = {}
        playlist._add_completion_exemptions(chance, "album", ["An Album"])

        assert chance == {"an album": 1.0}

    def test_the_cross_sort_case(self, mock_data_callbacks):
        """Played under composer grouping, demoted under album grouping. The album
        was never the grouping in force, so one track must not spend it."""
        library = _Library({"An Album": 20})
        playlist = _playlist(mock_data_callbacks, [], library)
        Playlist.update_recently_played_lists(_track(0), sort_type=PlaylistSortType.COMPOSER_SHUFFLE)

        chance = {}
        playlist._add_completion_exemptions(chance, "album", ["An Album"])

        assert chance == {"an album": 1.0}

    def test_a_stronger_existing_resistance_is_kept(self, mock_data_callbacks):
        library = _Library({"An Album": 15})
        playlist = _playlist(mock_data_callbacks, [], library)
        chance = {"an album": 0.3}

        playlist._add_completion_exemptions(chance, "album", ["An Album"])

        assert chance["an album"] == 1.0

    def test_favorites_resistance_for_other_values_is_untouched(self, mock_data_callbacks):
        library = _Library({"An Album": 15})
        playlist = _playlist(mock_data_callbacks, [], library)
        chance = {"something else": 0.4}

        playlist._add_completion_exemptions(chance, "album", ["An Album"])

        assert chance["something else"] == 0.4

    def test_derived_groupings_keep_the_old_behaviour(self, mock_data_callbacks):
        """The main artist and the catalogue are computed from other tags, so
        neither is what the listening log holds nor countable with a GROUP BY."""
        playlist = _playlist(mock_data_callbacks, [], _Library({}))

        for attr in ("get_main_artist", "get_catalogue"):
            chance = {}
            playlist._add_completion_exemptions(chance, attr, ["Anything"])
            assert chance == {}

    def test_an_unknown_group_size_is_not_exempted(self, mock_data_callbacks):
        """No answer from either source means no basis to exempt, so demotion
        behaves exactly as it does today."""
        playlist = _playlist(mock_data_callbacks, [], _Library({}))

        chance = {}
        playlist._add_completion_exemptions(chance, "album", ["Unknown Album"])

        assert chance == {}

    def test_a_failing_library_does_not_raise(self, mock_data_callbacks):
        class _Broken:
            def get_group_sizes(self, column, values):
                raise RuntimeError("database is locked")

        playlist = _playlist(mock_data_callbacks, [_track(0)], _Broken())
        record_listening(_track(0))

        chance = {}
        playlist._add_completion_exemptions(chance, "album", ["An Album"])

        # Fell back to the playlist's own count of 1, which that one play spends.
        assert chance == {}


@pytest.mark.unit
class TestGroupSizeFallback:
    def test_the_library_is_preferred(self, mock_data_callbacks):
        library = _Library({"An Album": 15})
        playlist = _playlist(mock_data_callbacks, [_track(0), _track(1)], library)

        sizes = playlist._group_sizes("album", "album", ["An Album"])

        assert sizes["An Album"] == 15
        assert library.asked == [("album", ["An Album"])]

    def test_the_playlist_answers_what_the_library_cannot(self, mock_data_callbacks):
        playlist = _playlist(mock_data_callbacks, [_track(0), _track(1), _track(2)], _Library({}))

        sizes = playlist._group_sizes("album", "album", ["An Album"])

        assert sizes["An Album"] == 3

    def test_no_library_at_all_is_survivable(self, mock_data_callbacks):
        playlist = _playlist(mock_data_callbacks, [_track(0), _track(1)])

        sizes = playlist._group_sizes("album", "album", ["An Album"])

        assert sizes["An Album"] == 2
