"""
Persistent playback session for "Continue Last Session" support.

At shutdown, the active playlist (resolved filepaths in playback order),
the currently-playing track, and the in-track position are written to
app_info_cache.  On the next launch the user can restore that exact state
with one button click.

A rolling list of the last MAX_RECENT_DESCRIPTORS playlist descriptors is
also maintained so that a history UI can surface them later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

LAST_SESSION_KEY = "last_playback_session"
RECENT_DESCRIPTORS_KEY = "recent_playlist_descriptors"
MAX_RECENT_DESCRIPTORS = 20


@dataclass
class PlaybackSession:
    resolved_tracks: List[str]
    current_track_filepath: str
    position_ms: int
    descriptor: Optional[dict] = None   # PlaylistDescriptor.to_dict() if available
    saved_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "resolved_tracks": self.resolved_tracks,
            "current_track_filepath": self.current_track_filepath,
            "position_ms": self.position_ms,
            "descriptor": self.descriptor,
            "saved_at": self.saved_at,
        }

    @staticmethod
    def from_dict(data: dict) -> PlaybackSession:
        return PlaybackSession(
            resolved_tracks=data.get("resolved_tracks", []),
            current_track_filepath=data.get("current_track_filepath", ""),
            position_ms=data.get("position_ms", 0),
            descriptor=data.get("descriptor"),
            saved_at=data.get("saved_at", ""),
        )


class PlaybackSessionStore:

    @staticmethod
    def save(session: PlaybackSession) -> None:
        from utils.app_info_cache import app_info_cache
        app_info_cache.set(LAST_SESSION_KEY, session.to_dict())

    @staticmethod
    def load() -> Optional[PlaybackSession]:
        from utils.app_info_cache import app_info_cache
        data = app_info_cache.get(LAST_SESSION_KEY)
        if not data or not isinstance(data, dict):
            return None
        try:
            return PlaybackSession.from_dict(data)
        except Exception:
            return None

    @staticmethod
    def push_recent_descriptor(descriptor_dict: dict) -> None:
        """Prepend to the recent-descriptors list, deduplicating by name."""
        from utils.app_info_cache import app_info_cache
        recents: list = app_info_cache.get(RECENT_DESCRIPTORS_KEY, []) or []
        name = descriptor_dict.get("name", "")
        recents = [d for d in recents if d.get("name") != name]
        recents.insert(0, descriptor_dict)
        app_info_cache.set(RECENT_DESCRIPTORS_KEY, recents[:MAX_RECENT_DESCRIPTORS])

    @staticmethod
    def load_recent_descriptors() -> List[dict]:
        from utils.app_info_cache import app_info_cache
        return app_info_cache.get(RECENT_DESCRIPTORS_KEY, []) or []
