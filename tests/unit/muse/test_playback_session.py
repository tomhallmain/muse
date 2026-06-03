"""
Unit tests for muse/playback_session.py.

Covers PlaybackSession serialization/deserialization and PlaybackSessionStore
save/load/recent-descriptor operations.

Isolation: the root conftest's autouse `isolated_singletons` fixture redirects
the app_info_cache singleton to a fresh in-memory AppInfoCache per test, so no
user data is touched and tests don't bleed state into one another.
"""

import pytest

from muse.playback_session import (
    PlaybackSession,
    PlaybackSessionStore,
    LAST_SESSION_KEY,
    RECENT_DESCRIPTORS_KEY,
    MAX_RECENT_DESCRIPTORS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_session(**kwargs):
    defaults = dict(
        resolved_tracks=["/music/a.flac", "/music/b.flac"],
        current_track_filepath="/music/a.flac",
        position_ms=42000,
        descriptor=None,
        saved_at="2026-01-01T00:00:00",
    )
    defaults.update(kwargs)
    return PlaybackSession(**defaults)


# ---------------------------------------------------------------------------
# PlaybackSession serialization
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPlaybackSessionSerialization:
    def test_to_dict_contains_all_fields(self):
        session = make_session()
        d = session.to_dict()
        assert d["resolved_tracks"] == ["/music/a.flac", "/music/b.flac"]
        assert d["current_track_filepath"] == "/music/a.flac"
        assert d["position_ms"] == 42000
        assert d["descriptor"] is None
        assert d["saved_at"] == "2026-01-01T00:00:00"

    def test_from_dict_round_trips(self):
        session = make_session(descriptor={"name": "Jazz"})
        restored = PlaybackSession.from_dict(session.to_dict())
        assert restored.resolved_tracks == session.resolved_tracks
        assert restored.current_track_filepath == session.current_track_filepath
        assert restored.position_ms == session.position_ms
        assert restored.descriptor == {"name": "Jazz"}
        assert restored.saved_at == session.saved_at

    def test_from_dict_missing_keys_use_defaults(self):
        restored = PlaybackSession.from_dict({})
        assert restored.resolved_tracks == []
        assert restored.current_track_filepath == ""
        assert restored.position_ms == 0
        assert restored.descriptor is None

    def test_descriptor_preserved_through_round_trip(self):
        descriptor = {"name": "Rock", "sort_type": "RANDOM", "directories": ["/music/rock"]}
        session = make_session(descriptor=descriptor)
        restored = PlaybackSession.from_dict(session.to_dict())
        assert restored.descriptor == descriptor


# ---------------------------------------------------------------------------
# PlaybackSessionStore save / load
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPlaybackSessionStore:
    def test_save_then_load_returns_same_session(self):
        session = make_session()
        PlaybackSessionStore.save(session)
        loaded = PlaybackSessionStore.load()
        assert loaded is not None
        assert loaded.resolved_tracks == session.resolved_tracks
        assert loaded.current_track_filepath == session.current_track_filepath
        assert loaded.position_ms == session.position_ms

    def test_load_with_no_stored_data_returns_none(self):
        assert PlaybackSessionStore.load() is None

    def test_load_with_corrupt_data_returns_none(self):
        from utils.app_info_cache import app_info_cache
        app_info_cache.set(LAST_SESSION_KEY, "not-a-dict")
        assert PlaybackSessionStore.load() is None

    def test_save_overwrites_previous_session(self):
        PlaybackSessionStore.save(make_session(current_track_filepath="/music/a.flac"))
        PlaybackSessionStore.save(make_session(current_track_filepath="/music/b.flac"))
        loaded = PlaybackSessionStore.load()
        assert loaded.current_track_filepath == "/music/b.flac"

    def test_push_recent_descriptor_prepends(self):
        PlaybackSessionStore.push_recent_descriptor({"name": "Jazz"})
        PlaybackSessionStore.push_recent_descriptor({"name": "Rock"})
        recents = PlaybackSessionStore.load_recent_descriptors()
        assert recents[0]["name"] == "Rock"
        assert recents[1]["name"] == "Jazz"

    def test_push_recent_descriptor_deduplicates_by_name(self):
        PlaybackSessionStore.push_recent_descriptor({"name": "Jazz", "version": 1})
        PlaybackSessionStore.push_recent_descriptor({"name": "Rock"})
        PlaybackSessionStore.push_recent_descriptor({"name": "Jazz", "version": 2})
        recents = PlaybackSessionStore.load_recent_descriptors()
        jazz_entries = [d for d in recents if d["name"] == "Jazz"]
        assert len(jazz_entries) == 1
        assert jazz_entries[0]["version"] == 2

    def test_recent_descriptors_capped_at_max(self):
        for i in range(MAX_RECENT_DESCRIPTORS + 5):
            PlaybackSessionStore.push_recent_descriptor({"name": str(i)})
        recents = PlaybackSessionStore.load_recent_descriptors()
        assert len(recents) == MAX_RECENT_DESCRIPTORS

    def test_load_recent_descriptors_with_empty_cache_returns_empty_list(self):
        assert PlaybackSessionStore.load_recent_descriptors() == []


# ---------------------------------------------------------------------------
# PlaybackConfig attribute: regression for pc.playlist vs pc.get_list()
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPlaybackConfigPlaylistAttribute:
    """Regression: _save_playback_session used pc.playlist (nonexistent) instead
    of pc.get_list().  Verify PlaybackConfig exposes get_list() not playlist."""

    def test_playback_config_has_no_playlist_attribute(self, mock_data_callbacks):
        from muse.playback_config import PlaybackConfig
        pc = PlaybackConfig(data_callbacks=mock_data_callbacks)
        assert not hasattr(pc, "playlist"), (
            "PlaybackConfig must not expose a 'playlist' attribute; "
            "use get_list() instead"
        )

    def test_playback_config_get_list_returns_playlist_instance(self, mock_data_callbacks):
        from muse.playback_config import PlaybackConfig
        from muse.playlist import Playlist
        pc = PlaybackConfig(data_callbacks=mock_data_callbacks, explicit_tracks=[])
        assert isinstance(pc.get_list(), Playlist)
