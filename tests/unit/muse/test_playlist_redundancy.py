"""
Unit tests for the playlist redundancy score feature.

Two areas covered:

1. _build_inclusion_chance — pure dict-construction logic, tested without
   constructing a full Playlist.

2. Resistance in scour_playlist — functional verification that the inclusion
   chance dict actually prevents (score=1.0) or allows (score=0.0) moves.
   Tests call scour_playlist directly so there is no dependence on the random
   shuffle path or the memory-history heuristics.
"""
import pytest

from muse.playlist import Playlist, _build_inclusion_chance, GROUP_REDUNDANCY_SCORE_KEY
from utils.globals import PlaylistSortType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _composer_fav(value: str) -> dict:
    """Minimal serialised Favorite for a COMPOSER attribute."""
    return {"attribute": "composer", "value": value, "timestamp": 1.0}


def _artist_fav(value: str) -> dict:
    return {"attribute": "artist", "value": value, "timestamp": 1.0}


def _title_fav(title: str, *, composer: str = "", artist: str = "", album: str = "") -> dict:
    """Minimal serialised track-title Favorite."""
    return {
        "attribute": "title",
        "value": title,
        "timestamp": 1.0,
        "artist": artist,
        "album": album,
        "composer": composer,
        "filepath": "",
    }


# ---------------------------------------------------------------------------
# _build_inclusion_chance
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBuildInclusionChance:

    def test_returns_empty_when_score_is_zero(self):
        result = _build_inclusion_chance("composer", 0.0)
        assert result == {}

    def test_returns_empty_when_no_favorites(self):
        # isolated_singletons gives a blank cache — no favorites stored
        result = _build_inclusion_chance("composer", 0.5)
        assert result == {}

    def test_direct_tier_composer(self, monkeypatch):
        import muse.playlist as pl_mod
        pl_mod.app_info_cache.set("favorites", [_composer_fav("Bach")])

        result = _build_inclusion_chance("composer", 0.5)
        assert result == {"bach": 0.5}

    def test_direct_tier_artist(self, monkeypatch):
        import muse.playlist as pl_mod
        pl_mod.app_info_cache.set("favorites", [_artist_fav("Miles Davis")])

        result = _build_inclusion_chance("artist", 0.8)
        assert result == {"miles davis": 0.8}

    def test_implied_tier_from_track_title_favorite(self, monkeypatch):
        import muse.playlist as pl_mod
        pl_mod.app_info_cache.set("favorites", [_title_fav("Any Title", composer="Debussy")])

        result = _build_inclusion_chance("composer", 0.5)
        # Implied score = 0.5 * 0.5 = 0.25
        assert result == {"debussy": pytest.approx(0.25)}

    def test_direct_tier_beats_implied_regardless_of_order(self, monkeypatch):
        """A direct attribute favorite must win even if an implied entry is seen first."""
        import muse.playlist as pl_mod
        # implied entry appears before direct in the list
        pl_mod.app_info_cache.set("favorites", [
            _title_fav("Track A", composer="Bach"),  # implied → 0.25
            _composer_fav("Bach"),                   # direct  → 0.5  (must win)
        ])

        result = _build_inclusion_chance("composer", 0.5)
        assert result == {"bach": 0.5}

    def test_direct_entry_is_not_overwritten_by_later_implied(self, monkeypatch):
        """A direct entry that appears before an implied one must not be downgraded."""
        import muse.playlist as pl_mod
        pl_mod.app_info_cache.set("favorites", [
            _composer_fav("Bach"),                   # direct  → 0.5
            _title_fav("Track A", composer="Bach"),  # implied should be ignored
        ])

        result = _build_inclusion_chance("composer", 0.5)
        assert result == {"bach": 0.5}

    def test_favorites_for_other_attributes_ignored(self, monkeypatch):
        """ARTIST favorites must not appear in a composer-shuffle inclusion dict."""
        import muse.playlist as pl_mod
        pl_mod.app_info_cache.set("favorites", [_artist_fav("Miles Davis")])

        result = _build_inclusion_chance("composer", 0.5)
        assert result == {}

    def test_malformed_favorite_entry_skipped(self, monkeypatch):
        """A corrupt cache entry must not crash or pollute the result."""
        import muse.playlist as pl_mod
        pl_mod.app_info_cache.set("favorites", [
            "not a dict",
            {"attribute": "INVALID_ATTR", "value": "x", "timestamp": 1.0},
            _composer_fav("Brahms"),
        ])

        result = _build_inclusion_chance("composer", 0.5)
        assert result == {"brahms": 0.5}

    def test_multiple_composers_all_present(self, monkeypatch):
        import muse.playlist as pl_mod
        pl_mod.app_info_cache.set("favorites", [
            _composer_fav("Bach"),
            _composer_fav("Mozart"),
        ])

        result = _build_inclusion_chance("composer", 1.0)
        assert result == {"bach": 1.0, "mozart": 1.0}

    def test_implied_from_album_attribute(self, monkeypatch):
        import muse.playlist as pl_mod
        pl_mod.app_info_cache.set("favorites", [_title_fav("Some Track", album="Kind of Blue")])

        result = _build_inclusion_chance("album", 0.6)
        assert result == {"kind of blue": pytest.approx(0.3)}


# ---------------------------------------------------------------------------
# Resistance in scour_playlist
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestScourPlaylistResistance:
    """Call scour_playlist directly to avoid dependence on the shuffle path."""

    @pytest.fixture
    def composer_playlist(self, mock_data_callbacks, mock_tracks):
        """A SEQUENCE playlist whose sorted_tracks we can freely rearrange."""
        return Playlist(
            tracks=[t.filepath for t in mock_tracks],
            _type=PlaylistSortType.SEQUENCE,
            data_callbacks=mock_data_callbacks,
        )

    def _beethoven_at_front(self, playlist) -> bool:
        """True if any Beethoven track is in the first recently_played_check_count positions."""
        check = 2  # we use check_count=2 in all tests below
        front = [t.composer for t in playlist.sorted_tracks[:check]]
        return "Beethoven" in front

    def test_score_one_prevents_move(self, composer_playlist, mock_tracks):
        """inclusion_chance=1.0 for Beethoven means Beethoven tracks always resist."""
        pl = composer_playlist
        # Put both Beethoven tracks at the very front
        beethoven = [t for t in mock_tracks if t.composer == "Beethoven"]
        others    = [t for t in pl.sorted_tracks if t.composer != "Beethoven"]
        pl.sorted_tracks = beethoven + others

        pl.scour_playlist(
            "composer",
            ["Beethoven"],
            recently_played_check_count=2,
            inclusion_chance={"beethoven": 1.0},
        )

        # Both Beethoven tracks must still occupy the first two positions
        front_composers = [t.composer for t in pl.sorted_tracks[:2]]
        assert front_composers == ["Beethoven", "Beethoven"]

    def test_score_zero_moves_all_tracks(self, composer_playlist, mock_tracks):
        """Empty inclusion_chance means Beethoven tracks are moved as normal."""
        pl = composer_playlist
        beethoven = [t for t in mock_tracks if t.composer == "Beethoven"]
        others    = [t for t in pl.sorted_tracks if t.composer != "Beethoven"]
        pl.sorted_tracks = beethoven + others

        pl.scour_playlist(
            "composer",
            ["Beethoven"],
            recently_played_check_count=2,
            inclusion_chance={},
        )

        # Neither of the first two positions should be Beethoven
        front_composers = [t.composer for t in pl.sorted_tracks[:2]]
        assert "Beethoven" not in front_composers
