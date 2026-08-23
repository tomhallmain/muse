"""Unit tests for LibraryData.ensure_album_artwork_consistency.

Artwork quality is driven purely by byte length here: the payloads are not
decodable images, so artwork_quality() falls back to length and the tests behave
the same whether or not Pillow is installed.
"""

import logging
import os

import pytest

from library_data.library_data import LibraryData
from library_data.media_track import MediaTrack
from utils.config import config

# 4x the bytes of LARGE, so a track scored with it always wins
HUGE = b"x" * 20000
# 5x the bytes of SMALL, comfortably past ARTWORK_IMPROVEMENT_RATIO
LARGE = b"x" * 5000
SMALL = b"x" * 1000
# only 1.2x SMALL, below the threshold
MARGINAL = b"x" * 1200

DIR = "/music/Some Artist/Album"


class _FakeTrack:
    def __init__(self, title, album, artwork=None, album_from_metadata=True, directory=DIR):
        self.title = title
        self.album = album
        self.artwork = artwork
        self.album_from_metadata = album_from_metadata
        self.filepath = os.path.join(directory, f"{title}.flac")
        self.write_count = 0

    def load_embedded_artwork(self):
        return self.artwork

    def update_metadata(self, metadata):
        self.artwork = metadata.get("artwork")
        self.write_count += 1
        return True


def _memo_key(track):
    """The (album, directory) pair ensure_album_artwork_consistency memoises under."""
    return (track.album, os.path.dirname(os.path.abspath(track.filepath)))


@pytest.fixture
def library_logs(caplog, monkeypatch):
    """Capture this module's log records.

    get_logger sets propagate=False, so records never reach the root logger that
    caplog attaches its handler to; propagation is turned back on for the test.
    """
    logger = logging.getLogger("muse.library_data.library_data")
    monkeypatch.setattr(logger, "propagate", True)
    caplog.set_level(logging.INFO, logger=logger.name)
    return caplog


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
        assert _memo_key(a) in LibraryData.albums_without_artwork

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

        assert _memo_key(b) not in LibraryData.albums_without_artwork


@pytest.mark.unit
class TestLogsSayWhatHappened:
    """A skipped check must say it was skipped and why, rather than announcing a
    start and a finish around work it never did."""

    def test_a_skip_gives_its_reason_and_claims_no_start(self, library_logs):
        a = _FakeTrack("a", "Unknown Album", LARGE, album_from_metadata=False)
        b = _FakeTrack("b", "Unknown Album", None, album_from_metadata=False)
        library = _library([a, b])

        library.ensure_album_artwork_consistency(b)

        assert "skipped" in library_logs.text
        assert "directory name" in library_logs.text
        assert "Starting album artwork consistency" not in library_logs.text
        assert "finished" not in library_logs.text

    def test_a_lone_track_says_nothing_else_shares_the_album(self, library_logs):
        a = _FakeTrack("a", "Album", LARGE)
        library = _library([a])

        library.ensure_album_artwork_consistency(a)

        assert "skipped" in library_logs.text
        assert "nothing else in" in library_logs.text

    def test_a_write_is_reported_with_its_count_and_source(self, library_logs):
        best = _FakeTrack("best", "Album", LARGE)
        poor = _FakeTrack("poor", "Album", SMALL)
        library = _library([best, poor])

        library.ensure_album_artwork_consistency(poor)

        assert "Starting album artwork consistency" in library_logs.text
        assert "wrote" in library_logs.text and "'best'" in library_logs.text
        assert "onto 1 of 1 albummates" in library_logs.text

    def test_doing_nothing_is_reported_as_doing_nothing(self, library_logs):
        a = _FakeTrack("a", "Album", LARGE)
        b = _FakeTrack("b", "Album", LARGE)
        library = _library([a, b])

        library.ensure_album_artwork_consistency(a)

        assert "nothing was changed" in library_logs.text

    def test_an_artless_album_says_so_and_says_it_will_not_re_read(self, library_logs):
        a = _FakeTrack("a", "Album", None)
        b = _FakeTrack("b", "Album", None)
        library = _library([a, b])

        library.ensure_album_artwork_consistency(a)

        assert "none of the 2 tracks carries any artwork" in library_logs.text

    def test_long_track_lists_are_cut_short(self):
        """One album ran to hundreds of tracks, which is not a log line."""
        assert LibraryData._few(["a", "b"]) == "a, b"
        assert LibraryData._few([str(n) for n in range(9)]) == "0, 1, 2, 3, 4 and 4 more"


@pytest.mark.unit
class TestAlbumMustBeMetadataDefined:
    """A directory name is not an album. Tracks land in one folder because the
    user put them there, which says nothing about what artwork they should share."""

    def test_directory_derived_album_is_skipped(self):
        a = _FakeTrack("a", "Unknown Album", LARGE, album_from_metadata=False)
        b = _FakeTrack("b", "Unknown Album", None, album_from_metadata=False)
        library = _library([a, b])

        assert library.ensure_album_artwork_consistency(b) is False
        assert b.artwork is None
        assert b.write_count == 0
        assert a.write_count == 0

    def test_untagged_albummates_are_not_a_source(self):
        """Tagged and untagged files can share a folder; only the tagged ones
        belong to the album, so an untagged file's artwork is never propagated."""
        tagged = _FakeTrack("tagged", "Album", SMALL)
        other_tagged = _FakeTrack("other_tagged", "Album", LARGE)
        untagged = _FakeTrack("untagged", "Album", HUGE, album_from_metadata=False)
        library = _library([tagged, other_tagged, untagged])

        assert library.ensure_album_artwork_consistency(tagged) is True

        # HUGE would have won had the untagged file been scored.
        assert tagged.artwork == LARGE
        assert untagged.write_count == 0

    def test_untagged_albummates_are_not_a_target(self):
        best = _FakeTrack("best", "Album", LARGE)
        tagged = _FakeTrack("tagged", "Album", SMALL)
        untagged = _FakeTrack("untagged", "Album", SMALL, album_from_metadata=False)
        library = _library([best, tagged, untagged])

        library.ensure_album_artwork_consistency(tagged)

        assert untagged.artwork == SMALL
        assert untagged.write_count == 0


@pytest.mark.unit
class TestAlbumPathBoundaries:
    """The same album name turns up in unrelated directories, under different
    artists and on different disks. Those are different albums."""

    C_DRIVE = "/c/audio/Unknown Artist/Unknown Album"
    F_DRIVE = "/f/iTunes Music/Dad Bowman/Unknown Album"

    def test_namesake_in_another_directory_is_not_an_albummate(self):
        here = _FakeTrack("here", "Unknown Album", None, directory=self.C_DRIVE)
        there_a = _FakeTrack("Side 1", "Unknown Album", LARGE, directory=self.F_DRIVE)
        there_b = _FakeTrack("Side 1-1", "Unknown Album", SMALL, directory=self.F_DRIVE)
        library = _library([here, there_a, there_b])

        assert library.ensure_album_artwork_consistency(here) is False

        assert here.artwork is None
        assert there_a.write_count == 0
        assert there_b.write_count == 0

    def test_each_directory_is_brought_into_line_on_its_own(self):
        there_a = _FakeTrack("Side 1", "Unknown Album", LARGE, directory=self.F_DRIVE)
        there_b = _FakeTrack("Side 1-1", "Unknown Album", SMALL, directory=self.F_DRIVE)
        elsewhere = _FakeTrack("elsewhere", "Unknown Album", SMALL, directory=self.C_DRIVE)
        library = _library([there_a, there_b, elsewhere])

        assert library.ensure_album_artwork_consistency(there_b) is True

        assert there_b.artwork == LARGE
        assert elsewhere.artwork == SMALL
        assert elsewhere.write_count == 0

    def test_artless_memo_does_not_suppress_a_namesake_elsewhere(self):
        artless_a = _FakeTrack("artless_a", "Unknown Album", None, directory=self.C_DRIVE)
        artless_b = _FakeTrack("artless_b", "Unknown Album", None, directory=self.C_DRIVE)
        has_art = _FakeTrack("has_art", "Unknown Album", LARGE, directory=self.F_DRIVE)
        needs_art = _FakeTrack("needs_art", "Unknown Album", None, directory=self.F_DRIVE)
        library = _library([artless_a, artless_b, has_art, needs_art])

        assert library.ensure_album_artwork_consistency(artless_a) is False
        assert _memo_key(artless_a) in LibraryData.albums_without_artwork

        assert library.ensure_album_artwork_consistency(needs_art) is True
        assert needs_art.artwork == LARGE
