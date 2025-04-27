from dataclasses import dataclass
from typing import Optional
import time

from utils.globals import TrackAttribute

@dataclass
class Favorite:
    """
    Represents a favorited item in the library.
    Can be a specific track (using TrackAttribute.TITLE) or any other track attribute.
    For track favorites, uses title as primary identifier with additional metadata
    to help locate the track if it moves.
    """
    attribute: TrackAttribute
    value: str  # The value of the attribute (e.g. title for TITLE, genre name for GENRE)
    value_lower: str = ""  # Lowercase version of the value
    timestamp: float = 0.0  # Unix timestamp for recency ordering
    # Additional metadata for track favorites
    artist: str = ""  # Track artist
    album: str = ""  # Track album
    composer: str = ""  # Track composer
    filepath: str = ""  # Last known filepath (for reference only)

    def __init__(self, attribute: TrackAttribute, value: str, timestamp: float = None,
                 artist: str = "", album: str = "", composer: str = "", filepath: str = ""):
        self.attribute = attribute
        self.value = value
        self.value_lower = value.lower() if value else ""
        self.timestamp = timestamp or time.time()
        self.artist = artist
        self.album = album
        self.composer = composer
        self.filepath = filepath

    @classmethod
    def from_track(cls, track):
        """Create a Favorite from a MediaTrack"""
        return cls(
            TrackAttribute.TITLE,
            track.title or track.filepath,  # Use title as primary identifier
            artist=track.artist or "",
            album=track.album or "",
            composer=track.composer or "",
            filepath=track.filepath
        )

    @classmethod
    def from_attribute(cls, attribute: TrackAttribute, value: str):
        """Create a Favorite from a track attribute"""
        return cls(attribute, value)

    def to_dict(self) -> dict:
        """Convert Favorite to dictionary for storage"""
        data = {
            "attribute": self.attribute.value,
            "value": self.value,
            "timestamp": self.timestamp
        }
        # Only include track metadata for track favorites
        if self.attribute == TrackAttribute.TITLE:
            data.update({
                "artist": self.artist,
                "album": self.album,
                "composer": self.composer,
                "filepath": self.filepath
            })
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'Favorite':
        """Create Favorite from dictionary"""
        return cls(
            TrackAttribute(data["attribute"]),
            data["value"],
            data.get("timestamp"),
            artist=data.get("artist", ""),
            album=data.get("album", ""),
            composer=data.get("composer", ""),
            filepath=data.get("filepath", "")
        )

    def matches_track(self, track) -> bool:
        """Check if this favorite matches a given track"""
        if self.attribute == TrackAttribute.TITLE:
            # Match by title and metadata
            return (self.value == (track.title or track.filepath) and
                    (not self.artist or self.artist == track.artist) and
                    (not self.album or self.album == track.album) and
                    (not self.composer or self.composer == track.composer))
        else:
            track_value = getattr(track, self.attribute.value, None)
            return track_value and self.value_lower in track_value.lower()

    def update_from_track(self, track) -> bool:
        """
        Update this favorite with new track information.
        Returns True if any changes were made.
        """
        if self.attribute != TrackAttribute.TITLE:
            return False
            
        changed = False
        if self.filepath != track.filepath:
            self.filepath = track.filepath
            changed = True
        if self.artist != track.artist:
            self.artist = track.artist or ""
            changed = True
        if self.album != track.album:
            self.album = track.album or ""
            changed = True
        if self.composer != track.composer:
            self.composer = track.composer or ""
            changed = True
        return changed

    def __eq__(self, other):
        if not isinstance(other, Favorite):
            return False
        if self.attribute == TrackAttribute.TITLE:
            # For track favorites, compare by title and metadata
            return (self.attribute == other.attribute and 
                    self.value == other.value and
                    self.artist == other.artist and
                    self.album == other.album and
                    self.composer == other.composer)
        else:
            return (self.attribute == other.attribute and 
                    self.value == other.value)

    def __hash__(self):
        if self.attribute == TrackAttribute.TITLE:
            # For track favorites, hash by title and metadata
            return hash((self.attribute, self.value, self.artist, 
                        self.album, self.composer))
        else:
            return hash((self.attribute, self.value)) 