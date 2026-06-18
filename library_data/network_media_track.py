"""NetworkMediaTrack — a MediaTrack backed by a live radio stream URL.

Bypasses MediaTrack.__init__'s file-loading (music_tag, MediaInfo) and
populates attributes directly from Radio Browser API data.
"""

from library_data.media_track import MediaTrack
from utils.translations import I18N

_ = I18N._


class NetworkMediaTrack(MediaTrack):
    """A MediaTrack that represents a live internet radio stream.

    VLC receives ``filepath`` as the stream URL and plays it natively.
    No local file operations are attempted.
    """

    def __init__(
        self,
        url: str,
        name: str,
        station_uuid: str = "",
        codec: str = "",
        bitrate: int = 0,
        tags: str = "",
        country: str = "",
    ) -> None:
        # Skip super().__init__() entirely — it calls music_tag.load_file(filepath)
        # which fails on http:// paths.  Every attribute that callers may access
        # is set explicitly below to safe defaults.
        self.filepath = url
        self.parent_filepath = None
        self.basename = name or url   # basename guards is_invalid()
        self.ext = ""
        self.tracktitle = name
        self.title = name
        self.artist = ""
        self.album = name  # station name; persists as the "Album" label after ICY updates title
        self.albumartist = ""
        self.composer = ""
        self.tracknumber = -1
        self.totaltracks = -1
        self.discnumber = -1
        self.totaldiscs = -1
        self.genre = tags
        self.year = None
        self.compilation = False
        self.compilation_name = None
        self.mean_volume = -9999.0
        self.max_volume = -9999.0
        self.length = -1.0          # sentinel: unknown / infinite
        self.artwork = None
        self.form = None
        self.instrument = None
        self.searchable_title = name.lower() if name else None
        self.searchable_album = None
        self.searchable_artist = None
        self.searchable_composer = None
        self.searchable_genre = tags.lower() if tags else None
        self._is_extended = False
        self.is_video = False
        self._is_stream = True      # checked via getattr() in app_qt without import
        # Radio Browser metadata (not on MediaTrack base)
        self.station_uuid = station_uuid
        self.stream_codec = codec
        self.stream_bitrate = bitrate
        self.country = country

    # ── MediaTrack interface overrides ───────────────────────────────────────

    def is_invalid(self) -> bool:
        return not self.filepath or not self.filepath.startswith("http")

    def is_stream(self) -> bool:
        return True

    def get_is_video(self) -> bool:
        return False

    def get_track_length(self) -> float:
        return -1.0

    def get_volume(self):
        return self.mean_volume, self.max_volume

    def get_album_artwork(self, filename: str = "image"):
        return None

    def open_track_location(self) -> None:
        pass

    def clean_track_values(self) -> None:
        pass

    def get_parent_filepath(self) -> str:
        return self.filepath

    def update_from_icy(self, artist: str, title: str) -> bool:
        """Update title and artist from an ICY StreamTitle update.

        Returns ``True`` if anything changed (triggers UI refresh).
        Only overwrites ``title`` when the new value is non-empty so that the
        station name set at construction remains visible until the first track
        metadata arrives.
        """
        if title == self.title and artist == self.artist:
            return False
        if title:
            self.title = title
            self.searchable_title = title.lower()
        self.artist = artist
        self.searchable_artist = artist.lower() if artist else ""
        return True

    def get_track_details(self) -> str:
        """Return a human-readable description including artist when known."""
        if self.title and self.artist:
            return f"{self.title} — {self.artist}"
        return self.title or self.filepath

    def readable_album(self) -> str:
        return _("Live Stream")

    def __str__(self) -> str:
        return f"{self.title} ({self.filepath})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, NetworkMediaTrack):
            return False
        return self.filepath == other.filepath

    def __hash__(self) -> int:
        return hash(self.filepath)
