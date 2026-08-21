"""Unit tests for LibraryData.ensure_album_artwork_consistency.

Artwork quality is driven purely by byte length here: the payloads are not
decodable images, so artwork_quality() falls back to length and the tests behave
the same whether or not Pillow is installed.
"""

import pytest

from library_data.library_data import LibraryData
from library_data.media_track import MediaTrack
from utils.config import config

# 5x the bytes of SMALL, comfortably past ARTWORK_IMPROVEMENT_RATIO
LARGE = b"x" * 5000
SMALL = b"x" * 1000
# only 1.2x SMALL, below the threshold
MARGINAL = b"x" * 1200


class _FakeTrack:
    def __init__(self, title, album, artwork=None):
        self.title = title
        self.album = album
        self.artwork = artwork
        self.write_count = 0

    def load_embedded_artwork(self):
        return self.artwork

    def update_metadata(self, metadata):
        self.artwork = metadata.get("artwork")
        self.write_count += 1
        return True


@pytest.fixture(autouse=True)
def artwork_enabled(monkeypatch):
    monkeypatch.setattr(config, "auto_fix_album_artwork", True)
    saved = LibraryData.all_tracks
    LibraryData.albums_without_artwork = set()
    yield
    LibraryData.all_tracks = saved
    LibraryData.albums_without_artwork = set()


def _library(tracks):
    LibraryData.all_tracks = tracks
    return LibraryData.__new__(LibraryData)


@pytest.mark.unit
class TestArtworkConsistencyGuards:
    def test_disabled_by_config(self, monkeypatch):
        monkeypatch.setattr(config, "auto_fix_album_artwork", False)
        a = _FakeTrack("a", "Album", LARGE)
        b = _FakeTrack("b", "Album", None)
        library = _library([a, b])

        assert library.ensure_album_artwork_consistency(a) is False
        assert b.write_count == 0

    def test_track_with_no_album(self):
        a = _FakeTrack("a", None, LARGE)
        library = _library([a])
        assert library.ensure_album_artwork_consistency(a) is False

    def test_single_track_album_is_left_alone(self):
        a = _FakeTrack("a", "Album", None)
        library = _library([a])
        assert library.ensure_album_artwork_consistency(a) is False
        assert a.write_count == 0


@pytest.mark.unit
class TestArtworkPropagation:
    def test_best_artwork_fills_a_track_that_has_none(self):
        a = _FakeTrack("a", "Album", LARGE)
        b = _FakeTrack("b", "Album", None)
        library = _library([a, b])

        assert library.ensure_album_artwork_consistency(b) is True
        assert b.artwork == LARGE
        assert a.write_count == 0

    def test_lower_quality_track_is_upgraded(self):
        a = _FakeTrack("a", "Album", LARGE)
        b = _FakeTrack("b", "Album", SMALL)
        library = _library([a, b])

        assert library.ensure_album_artwork_consistency(b) is True
        assert b.artwork == LARGE

    def test_higher_quality_track_is_never_downgraded(self):
        """The reported symptom: a more compressed copy overwriting a better one."""
        best = _FakeTrack("best", "Album", LARGE)
        poor = _FakeTrack("poor", "Album", SMALL)
        library = _library([best, poor])

        # Called with the poor track: the better one must still win.
        library.ensure_album_artwork_consistency(poor)

        assert best.artwork == LARGE
        assert best.write_count == 0

    def test_marginal_improvement_is_not_written(self):
        a = _FakeTrack("a", "Album", MARGINAL)
        b = _FakeTrack("b", "Album", SMALL)
        library = _library([a, b])

        assert library.ensure_album_artwork_consistency(b) is False
        assert b.artwork == SMALL
        assert b.write_count == 0

    def test_identical_artwork_is_not_rewritten(self):
        a = _FakeTrack("a", "Album", LARGE)
        b = _FakeTrack("b", "Album", LARGE)
        library = _library([a, b])

        assert library.ensure_album_artwork_consistency(a) is False
        assert a.write_count == 0
        assert b.write_count == 0

    def test_other_albums_are_untouched(self):
        a = _FakeTrack("a", "Album", LARGE)
        b = _FakeTrack("b", "Album", None)
        other = _FakeTrack("other", "Different Album", None)
        library = _library([a, b, other])

        library.ensure_album_artwork_consistency(b)

        assert other.artwork is None
        assert other.write_count == 0


@pytest.mark.unit
class TestArtlessAlbumMemo:
    def test_album_with_no_artwork_is_recorded_and_skipped(self):
        a = _FakeTrack("a", "Album", None)
        b = _FakeTrack("b", "Album", None)
        library = _library([a, b])

        assert library.ensure_album_artwork_consistency(a) is False
        assert "Album" in LibraryData.albums_without_artwork

        # A second pass must short-circuit rather than rescan; if it did not, the
        # album would be rescanned once for every track played from it.
        a.artwork = LARGE
        assert library.ensure_album_artwork_consistency(b) is False
        assert b.write_count == 0

    def test_album_with_artwork_is_not_recorded(self):
        a = _FakeTrack("a", "Album", LARGE)
        b = _FakeTrack("b", "Album", None)
        library = _library([a, b])

        library.ensure_album_artwork_consistency(b)

        assert "Album" not in LibraryData.albums_without_artwork
