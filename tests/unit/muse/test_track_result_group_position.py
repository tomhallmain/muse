"""Tests for TrackResult group_position, group_total, and current_grouping fields.

Verifies that next_track() correctly populates these fields throughout a group,
including mid-group advances where old_grouping/new_grouping are both None.
"""
import pytest
from muse import Playlist
from tests.conftest import MockMediaTrack, MockDataCallbacks
from utils.globals import PlaylistSortType


def _make_tracks(*specs):
    """Build MockMediaTrack list from (filepath, composer, album) tuples."""
    tracks = []
    for filepath, composer, album in specs:
        tracks.append(MockMediaTrack(
            filepath=filepath,
            title=filepath,
            album=album,
            artist="Test Artist",
            composer=composer,
            _genre="Classical",
            _form="Symphony",
            _instrument="Orchestra",
        ))
    return tracks


def _drain(playlist):
    """Advance through all tracks and return all TrackResults."""
    results = []
    while True:
        r = playlist.next_track()
        if r.track is None:
            break
        results.append(r)
    return results


@pytest.fixture(autouse=True)
def _clear_recently_played():
    """Isolate recently-played lists so shuffle history doesn't affect order."""
    originals = {
        "filepaths": Playlist.recently_played_filepaths[:],
        "albums": Playlist.recently_played_albums[:],
        "artists": Playlist.recently_played_artists[:],
        "composers": Playlist.recently_played_composers[:],
        "genres": Playlist.recently_played_genres[:],
        "forms": Playlist.recently_played_forms[:],
        "instruments": Playlist.recently_played_instruments[:],
    }
    Playlist.recently_played_filepaths = []
    Playlist.recently_played_albums = []
    Playlist.recently_played_artists = []
    Playlist.recently_played_composers = []
    Playlist.recently_played_genres = []
    Playlist.recently_played_forms = []
    Playlist.recently_played_instruments = []
    yield
    for k, v in originals.items():
        setattr(Playlist, f"recently_played_{k}", v)


@pytest.mark.unit
class TestGroupPositionNonGroupingSort:
    def test_sequence_sort_yields_no_group_info(self):
        tracks = _make_tracks(
            ("a.mp3", "Bach", "Album A"),
            ("b.mp3", "Bach", "Album A"),
        )
        pl = Playlist(
            tracks=[t.filepath for t in tracks],
            _type=PlaylistSortType.SEQUENCE,
            data_callbacks=MockDataCallbacks(tracks),
        )
        results = _drain(pl)
        for r in results:
            assert r.group_position is None
            assert r.group_total is None
            assert r.current_grouping is None


@pytest.mark.unit
class TestGroupPositionComposerShuffle:
    def _make_composer_playlist(self, tracks):
        return Playlist(
            tracks=[t.filepath for t in tracks],
            _type=PlaylistSortType.COMPOSER_SHUFFLE,
            data_callbacks=MockDataCallbacks(tracks),
        )

    def test_single_track_group_has_position_1_of_1(self):
        tracks = _make_tracks(
            ("solo.mp3", "Handel", "Messiah"),
        )
        pl = self._make_composer_playlist(tracks)
        results = _drain(pl)
        assert len(results) == 1
        assert results[0].current_grouping == "Handel"
        assert results[0].group_position == 1
        assert results[0].group_total == 1

    def test_first_track_in_group_has_position_1(self):
        tracks = _make_tracks(
            ("b1.mp3", "Bach", "WTC"),
            ("b2.mp3", "Bach", "WTC"),
            ("b3.mp3", "Bach", "WTC"),
        )
        pl = self._make_composer_playlist(tracks)
        results = _drain(pl)
        assert all(r.current_grouping == "Bach" for r in results)
        assert results[0].group_position == 1
        assert results[0].group_total == 3

    def test_mid_group_position_increments(self):
        """Each successive track in the same group should increment group_position."""
        tracks = _make_tracks(
            ("b1.mp3", "Bach", "WTC"),
            ("b2.mp3", "Bach", "WTC"),
            ("b3.mp3", "Bach", "WTC"),
        )
        pl = self._make_composer_playlist(tracks)
        results = _drain(pl)
        positions = [r.group_position for r in results]
        assert positions == [1, 2, 3]

    def test_group_total_is_consistent_across_group(self):
        """group_total must be the same for every track in the group."""
        tracks = _make_tracks(
            ("b1.mp3", "Bach", "WTC"),
            ("b2.mp3", "Bach", "WTC"),
            ("b3.mp3", "Bach", "WTC"),
        )
        pl = self._make_composer_playlist(tracks)
        results = _drain(pl)
        totals = {r.group_total for r in results}
        assert totals == {3}

    def test_current_grouping_populated_mid_group(self):
        """current_grouping must be set even when old_grouping and new_grouping are None.

        Tracks 2 and 3 of a group have no grouping boundary, so old_grouping and
        new_grouping are both None — but current_grouping must still reflect the group.
        """
        tracks = _make_tracks(
            ("b1.mp3", "Bach", "WTC"),
            ("b2.mp3", "Bach", "WTC"),
            ("b3.mp3", "Bach", "WTC"),
        )
        pl = self._make_composer_playlist(tracks)
        results = _drain(pl)
        # First result has a group boundary (old=None, new="Bach")
        assert results[0].new_grouping == "Bach"
        # Mid-group results have no boundary signal
        assert results[1].old_grouping is None
        assert results[1].new_grouping is None
        assert results[2].old_grouping is None
        assert results[2].new_grouping is None
        # But current_grouping must always be set
        for r in results:
            assert r.current_grouping == "Bach"

    def test_separate_groups_have_independent_positions(self):
        """Tracks in different groups must each start at position 1 with their own total."""
        tracks = _make_tracks(
            ("b1.mp3", "Bach", "WTC"),
            ("b2.mp3", "Bach", "WTC"),
            ("v1.mp3", "Vivaldi", "Four Seasons"),
        )
        pl = self._make_composer_playlist(tracks)
        results = _drain(pl)
        by_group = {}
        for r in results:
            by_group.setdefault(r.current_grouping, []).append(r)

        assert by_group["Bach"][0].group_position == 1
        assert by_group["Bach"][1].group_position == 2
        assert by_group["Bach"][0].group_total == 2
        assert by_group["Vivaldi"][0].group_position == 1
        assert by_group["Vivaldi"][0].group_total == 1
