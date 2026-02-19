import os
from dataclasses import dataclass
from typing import Dict, List, Optional, TYPE_CHECKING

from utils.globals import PlaylistSortType
from utils.logging_setup import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from library_data.library_data import LibraryData, LibraryDataSearch


NAMED_PLAYLISTS_CACHE_KEY = "playlist_descriptors"


@dataclass
class NamedPlaylist:
    """Persistent definition of a user-created playlist.

    A playlist is a set of instructions for producing a track list, not
    necessarily a resolved list of tracks. It supports three source modes:

    - **search_query**: A ``LibraryDataSearch.to_json()`` dict that is
      re-executed against the current library at runtime. Avoids staleness
      and aligns with the saved-searches UX in ``SearchWindow``.
    - **source_directories**: One or more directory paths whose media files
      become the track list.
    - **track_filepaths**: An explicit, ordered list of file paths
      (hand-curated or a snapshot of resolved search results that have been
      manually reordered).

    Exactly one source mode should be populated.
    """

    name: str

    # Track source -- exactly one of these should be populated.
    search_query: Optional[dict] = None
    source_directories: Optional[List[str]] = None
    track_filepaths: Optional[List[str]] = None

    # Sorting
    sort_type: PlaylistSortType = PlaylistSortType.SEQUENCE

    # Playback behaviour
    loop: bool = False

    # Metadata
    created_at: Optional[str] = None
    description: Optional[str] = None

    # ------------------------------------------------------------------
    # Source-mode helpers
    # ------------------------------------------------------------------

    def is_search_based(self) -> bool:
        return self.search_query is not None and len(self.search_query) > 0

    def is_directory_based(self) -> bool:
        return self.source_directories is not None and len(self.source_directories) > 0

    def is_track_based(self) -> bool:
        return self.track_filepaths is not None and len(self.track_filepaths) > 0

    def get_source_description(self) -> str:
        """Return a human-readable summary of the track source."""
        if self.is_search_based():
            parts = []
            for key in ("all", "title", "album", "artist", "composer",
                        "genre", "instrument", "form"):
                val = self.search_query.get(key, "")
                if val:
                    parts.append(f'{key}: "{val}"')
            return "Search: " + ", ".join(parts) if parts else "Search: (empty)"
        if self.is_directory_based():
            dirs = [os.path.basename(d) or d for d in self.source_directories]
            return "Directories: " + ", ".join(dirs)
        if self.is_track_based():
            count = len(self.track_filepaths)
            return f"Tracks: {count} track{'s' if count != 1 else ''}"
        return "(no source)"

    def is_reshuffle_redundant(self) -> bool:
        """Whether re-sorting this descriptor's tracks would be a no-op.

        Currently only SEQUENCE playlists are truly redundant: their order is
        hand-curated and ``skip_memory_shuffle`` prevents reordering.

        Single-attribute searches whose sort type matches the attribute are
        *not* redundant because memory-based reshuffling still re-evaluates
        recently-played history on each call.
        """
        return self.sort_type == PlaylistSortType.SEQUENCE

    def can_freeze(self) -> bool:
        """Return True if this playlist can be frozen to an explicit track list."""
        return self.is_search_based() or self.is_directory_based()

    def freeze_to_tracks(self, library_data: 'LibraryData') -> int:
        """Resolve the current source and convert to an explicit track list.

        Clears ``search_query`` and ``source_directories``, replacing them
        with the resolved ``track_filepaths``.  The caller is responsible
        for persisting the updated object via ``NamedPlaylistStore.save()``.

        Returns:
            The number of resolved tracks.

        Raises:
            ValueError: If the playlist is already track-based or has no
                resolvable source.
        """
        if self.is_track_based():
            raise ValueError(
                f"Playlist '{self.name}' is already track-based; "
                "nothing to freeze."
            )
        filepaths = self.resolve_tracks(library_data)
        self.search_query = None
        self.source_directories = None
        self.track_filepaths = filepaths
        logger.info(
            f"Froze playlist '{self.name}' to {len(filepaths)} explicit tracks"
        )
        return len(filepaths)

    # ------------------------------------------------------------------
    # Track resolution
    # ------------------------------------------------------------------

    def resolve_tracks(self, library_data: 'LibraryData') -> List[str]:
        """Resolve the playlist instructions into an ordered list of filepaths.

        * **search_query** -- runs the query against the current library via
          ``LibraryData.do_search()``.
        * **source_directories** -- delegates to
          ``LibraryData.get_all_filepaths()``.
        * **track_filepaths** -- returns the stored list with stale (missing)
          entries filtered out and a warning logged for each.

        Args:
            library_data: A ``LibraryData`` instance (needed for search and
                directory resolution).

        Returns:
            An ordered list of absolute file paths.

        Raises:
            ValueError: If no source mode is populated.
        """
        if self.is_search_based():
            return self._resolve_search(library_data)
        if self.is_directory_based():
            return self._resolve_directories(library_data)
        if self.is_track_based():
            return self._resolve_explicit_tracks()
        raise ValueError(
            f"NamedPlaylist '{self.name}' has no source mode set "
            "(search_query, source_directories, or track_filepaths)"
        )

    def _resolve_search(self, library_data: 'LibraryData') -> List[str]:
        from library_data.library_data import LibraryDataSearch

        query_dict = dict(self.search_query)
        # Remove UI-specific / non-query fields that shouldn't be passed to
        # the search constructor, or that we want to override.
        query_dict.pop("stored_results_count", None)
        query_dict.pop("selected_track_path", None)
        # Remove the max_results cap so we get all matching tracks.
        query_dict["max_results"] = 100_000
        query_dict["offset"] = 0

        search = LibraryDataSearch(**query_dict)
        library_data.do_search(search, overwrite=False)
        filepaths = [track.filepath for track in search.get_results()]
        logger.info(
            f"NamedPlaylist '{self.name}': search resolved {len(filepaths)} tracks"
        )
        return filepaths

    def _resolve_directories(self, library_data: 'LibraryData') -> List[str]:
        from library_data.library_data import LibraryData as LD
        from utils.utils import Utils

        # Validate each directory with retry logic before passing to
        # get_all_filepaths.  External / network drives on Windows may be
        # asleep and need a moment to spin up.
        valid_dirs = []
        for d in self.source_directories:
            if Utils.isdir_with_retry(d):
                valid_dirs.append(d)
            else:
                logger.warning(
                    f"NamedPlaylist '{self.name}': directory not found "
                    f"(even after retries): {d}"
                )

        if not valid_dirs:
            logger.warning(
                f"NamedPlaylist '{self.name}': no valid directories found"
            )
            return []

        filepaths = LD.get_all_filepaths(valid_dirs)
        logger.info(
            f"NamedPlaylist '{self.name}': directory source resolved "
            f"{len(filepaths)} tracks from {len(valid_dirs)} "
            f"director{'y' if len(valid_dirs) == 1 else 'ies'}"
        )
        return filepaths

    def _resolve_explicit_tracks(self) -> List[str]:
        from utils.utils import Utils

        # Use retry-aware file checks so that tracks on external / network
        # drives that may be in a sleep state are not prematurely discarded.
        valid = []
        stale_count = 0
        for fp in self.track_filepaths:
            if Utils.isfile_with_retry(fp):
                valid.append(fp)
            else:
                stale_count += 1
                logger.warning(
                    f"NamedPlaylist '{self.name}': stale track removed: {fp}"
                )
        if stale_count > 0:
            logger.warning(
                f"NamedPlaylist '{self.name}': {stale_count} stale track(s) "
                f"removed, {len(valid)} remaining"
            )
        return valid

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dict for ``app_info_cache`` storage."""
        data: dict = {"name": self.name}

        if self.search_query is not None:
            data["search_query"] = self.search_query
        if self.source_directories is not None:
            data["source_directories"] = self.source_directories
        if self.track_filepaths is not None:
            data["track_filepaths"] = self.track_filepaths

        data["sort_type"] = self.sort_type.value
        data["loop"] = self.loop

        if self.created_at is not None:
            data["created_at"] = self.created_at
        if self.description is not None:
            data["description"] = self.description

        return data

    @staticmethod
    def from_dict(data: dict) -> 'NamedPlaylist':
        """Deserialise from a ``app_info_cache`` dict."""
        sort_type_raw = data.get("sort_type", PlaylistSortType.SEQUENCE.value)
        if isinstance(sort_type_raw, PlaylistSortType):
            sort_type = sort_type_raw
        else:
            sort_type = PlaylistSortType.get(str(sort_type_raw))

        return NamedPlaylist(
            name=data["name"],
            search_query=data.get("search_query"),
            source_directories=data.get("source_directories"),
            track_filepaths=data.get("track_filepaths"),
            sort_type=sort_type,
            loop=data.get("loop", False),
            created_at=data.get("created_at"),
            description=data.get("description"),
        )

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        return f"{self.name} ({self.get_source_description()}, {self.sort_type.value})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, NamedPlaylist):
            return False
        return self.name == other.name

    def __hash__(self) -> int:
        return hash(self.name)


# ======================================================================
# Store
# ======================================================================

class NamedPlaylistStore:
    """CRUD operations for :class:`NamedPlaylist` objects.

    Thin, stateless wrapper around ``app_info_cache``.  Every method accepts
    an optional *cache* parameter so callers from either the Tkinter or Qt
    code-path can pass the appropriate ``app_info_cache`` instance.  When
    *cache* is ``None`` the Tkinter-side singleton is imported as the default.
    """

    @staticmethod
    def _get_cache(cache=None):
        if cache is not None:
            return cache
        from utils.app_info_cache import app_info_cache
        return app_info_cache

    @staticmethod
    def _get_all_raw(cache=None) -> dict:
        return NamedPlaylistStore._get_cache(cache).get(
            NAMED_PLAYLISTS_CACHE_KEY, {}
        )

    @staticmethod
    def _put_all_raw(data: dict, cache=None) -> None:
        NamedPlaylistStore._get_cache(cache).set(
            NAMED_PLAYLISTS_CACHE_KEY, data
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def load_all(cache=None) -> Dict[str, NamedPlaylist]:
        """Return all named playlists keyed by name."""
        raw = NamedPlaylistStore._get_all_raw(cache)
        playlists: Dict[str, NamedPlaylist] = {}
        for name, data in raw.items():
            try:
                playlists[name] = NamedPlaylist.from_dict(data)
            except Exception:
                logger.exception(f"Failed to load named playlist '{name}'")
        return playlists

    @staticmethod
    def save(playlist: NamedPlaylist, cache=None) -> None:
        """Save (insert or update) a named playlist."""
        raw = NamedPlaylistStore._get_all_raw(cache)
        raw[playlist.name] = playlist.to_dict()
        NamedPlaylistStore._put_all_raw(raw, cache)

    @staticmethod
    def delete(name: str, cache=None) -> bool:
        """Delete a named playlist by name.  Returns True if it existed."""
        raw = NamedPlaylistStore._get_all_raw(cache)
        if name in raw:
            del raw[name]
            NamedPlaylistStore._put_all_raw(raw, cache)
            return True
        return False

    @staticmethod
    def get(name: str, cache=None) -> Optional[NamedPlaylist]:
        """Retrieve a single named playlist, or None if not found."""
        raw = NamedPlaylistStore._get_all_raw(cache)
        data = raw.get(name)
        if data is None:
            return None
        try:
            return NamedPlaylist.from_dict(data)
        except Exception:
            logger.exception(f"Failed to load named playlist '{name}'")
            return None

    @staticmethod
    def rename(old_name: str, new_name: str, cache=None) -> bool:
        """Rename a named playlist.  Returns True on success."""
        raw = NamedPlaylistStore._get_all_raw(cache)
        if old_name not in raw:
            logger.warning(f"Cannot rename: playlist '{old_name}' not found")
            return False
        if new_name in raw:
            logger.warning(
                f"Cannot rename: playlist '{new_name}' already exists"
            )
            return False
        data = raw.pop(old_name)
        data["name"] = new_name
        raw[new_name] = data
        NamedPlaylistStore._put_all_raw(raw, cache)
        return True

    @staticmethod
    def exists(name: str, cache=None) -> bool:
        """Check whether a named playlist with the given name exists."""
        return name in NamedPlaylistStore._get_all_raw(cache)
